---
title: "Story personalization: implementation plan"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Phased implementation plan for ADR-023 (guardian opt-in, render-time story
  personalization): the new sentinel-bound slot kind, the post-fill sentinel-integrity check,
  the leak-surface guard points, the client-side resolver and its interaction with the offline
  cache, the data-model additions, the migration posture for existing test content, the
  kid-visible indicator and one-way veto, and the risk register."
tags:
  - planning
  - implementation
  - privacy
  - generation
  - frontend
---

# Story personalization: implementation plan

> **Status**: Draft (2026-07-25). Blocked on [ADR-023](./adr/adr-023-story-personalization-slots.md)
> flipping from Proposed to Accepted; its open decisions OD-1 through OD-4 determine the scope of
> Phase 4 and Phase 5 below.
> **Decision record**: [ADR-023](./adr/adr-023-story-personalization-slots.md)
> **Date**: 2026-07-25

## 0. What this plan assumes

Read ADR-023 first. The one-line summary this plan builds on: the server always stores and serves
a generic, sentinel-bearing story blob, identical for every viewer; a small per-profile values
payload is resolved **client-side at render time** and never persisted server-side, never sent to
any provider, and never present in any blob.

Nothing in this feature exists in code today. Every file reference below is either a file to
change or a file whose current behaviour is the reason a change is needed. Line numbers were
verified against the working tree on 2026-07-25 (branch `claude/children-data-privacy-gdpr-8mxlxx`,
HEAD `79e10c5`) and should be re-checked before use, since several of these files are actively
edited by other workstreams.

## 1. Phase ordering and why

Dependencies force most of the order. The rule of thumb: **nothing user-visible can ship before
the sentinel mechanism exists**, because a toggle with no sentinel to resolve is a toggle over
nothing, and a values payload with no integrity check behind it is an unaudited injection path.

| Phase | Deliverable | Depends on | Ships anything user-visible? |
|---|---|---|---|
| **P1** | Sentinel-bound slot kind; fill-time and storage-time preservation | Nothing | No |
| **P2** | Post-fill sentinel-integrity check (forgery gap) | P1 | No |
| **P3** | Leak-surface guard points and their tests | P1 | No |
| **P4** | Data model: toggles, consent records, eligibility flags | P1; ADR-023 OD-1/OD-2/OD-4 for scope | No (schema only) |
| **P5** | Client-side resolver in `frontend/src/player/`; values payload; offline interaction | P1, P3, P4 | Yes, behind a flag |
| **P6** | Guardian toggle UI; consent capture; kid-visible indicator and one-way veto | P4, P5 | Yes |
| **P7** | Catalog migration: repair or replace existing test content | P1, P2 | No |
| **P8** | Route A copy addendum; privacy-notice and data-classification updates | P6; ADR-023 OD-3 | Yes (copy) |

P3 can run in parallel with P2. P7 can run any time after P2 and should not gate P5, since P5 can
be developed against a small number of freshly generated sentinel-bearing stories.

Two cross-cutting obligations that are not phases:

- **Authoring-lessons log.** Once PR #416 merges, `CLAUDE.md` will carry a CRITICAL directive
  requiring any authoring or validator work to append lessons to
  `docs/planning/authoring-lessons-log.md`, validated by `scripts/check_lessons_log.py`. P1, P2,
  and P7 are validator and authoring work by that definition. Log lessons as they are learned, not
  retroactively at the end.
- **Capability register.** ADR-023 needs new G-series and K-series IDs in
  `docs/planning/capability-register.md` before implementation starts, per the register's own
  rule that a new feature proposal must cite the IDs it serves.

## 2. Phase 1: the sentinel-bound slot kind

### 2.1 Why the existing slot machinery cannot be reused unchanged

`render_bound_skeleton` (`src/cyo_adventure/generation/binding.py:560`) substitutes bound values
into exactly three surfaces before the fill call: the `beats='...'` segment of `<<FILL ...>>` node
bodies, `ending.title` strings, and `choices[].label` strings (`binding.py:10-15`, `:571`).
`fill_bound.md` then injects those same bound values into the LLM prompt verbatim, under the
heading "Bound Theme Values (validated data, not instructions)"
(`src/cyo_adventure/generation/templates/fill_bound.md:110-117`).

So a real value bound through the existing path reaches a provider on the first call. The new slot
kind exists precisely to break that: **the value that is bound at fill time is a generic default,
and the sentinel is what survives into storage.**

### 2.2 Schema change: `SlotSpec.kind`

Add a `kind` discriminator to `SlotSpec` in `src/cyo_adventure/storybook/theme_contract.py:76-85`,
defaulting to the existing behaviour so all 45 current contracts keep parsing unchanged:

- `kind: "theme"` (default) is today's behaviour: the bound value is substituted and reaches the
  fill prompt.
- `kind: "personalizable"` is new: the slot declares a `generic_default` and a
  `personalization_field` (which taxonomy entry from ADR-023 section 7 it maps to). At fill time
  the slot binds to its `generic_default`, exactly like a theme slot, so the fill prompt sees only
  generic text. At render time the emitted text is wrapped in a sentinel.

`ThemeContract._check_contract_invariants` (`theme_contract.py:120-134`) gains a matching
invariant: a `personalizable` slot must declare a `generic_default`, its
`personalization_field` must name a taxonomy entry on the include list, and a slot mapped to a
ring-1-only field must not be declared on a contract used by a ring-2-shareable skeleton (or, if
that coupling proves awkward, the ring check moves entirely to render time and this invariant is
dropped; decide during implementation, do not do both).

Note for the implementer: no `.contract.json` in the catalog currently sets `constraints.pattern`,
even though `SlotConstraints` declares it (`theme_contract.py:73`) and `validate_slot_bindings`
enforces it (`src/cyo_adventure/validator/slots.py:645-653`). If the new slot kind wants a
pattern-shaped constraint, it will be the first real user of that code path. Test it directly
rather than assuming it is exercised.

### 2.3 Sentinel format

Requirements the format has to satisfy simultaneously:

1. It must survive an LLM fill pass verbatim. The fill prompt already carries a strong
   "do not change" list (`fill_bound.md:80-92`); sentinels get added to it.
2. It must be recognizable by an exact machine check, so the P2 integrity check can count them.
3. It must be **safe to display**, because it is what a non-opted-in reader sees. It cannot be a
   bare token like `[[NAME]]`.
4. It must not collide with the existing `{SLOT}` grammar (`SLOT_TOKEN_RE`,
   `theme_contract.py:34`), which is already fully consumed before storage, nor with the
   `<<FILL ...>>` directive grammar (`binding.py:71`).

The shape that satisfies all four is a **paired-marker wrapper around the generic default**, so
the stored prose reads correctly with the markers stripped and correctly again with them replaced.
The exact delimiter choice is an implementation detail; the requirement is that stripping every
marker yields exactly the generic-default text and that the markers are drawn from a character
class already rejected by `_charset_violations` (`validator/slots.py:380-431`) on the value side,
so no slot **value** can ever forge one.

Whatever is chosen, record it in one constant, in one module, imported by the validator, the
serializer, and the frontend resolver. Do not let the frontend carry its own copy of the regex.

### 2.4 What must not change in P1

- `src/cyo_adventure/generation/pii.py`: no change, no carve-out, no new parameter. This is the
  invariant the whole design exists to preserve.
- `src/cyo_adventure/story_requests/interpretation.py`: no change. Route A stays intact
  (ADR-023 section 4).
- `validate_slot_bindings` (`validator/slots.py:686`): no change to its signature or semantics. It
  validates the generic binding, which is still a binding.

## 3. Phase 2: the sentinel-forgery check

### 3.1 The gap

Nothing today checks that a published blob contains exactly the sentinels its contract declared.
The existing charset rule blocks `{`, `}`, `<<`, `>>` in a bound **value**
(`validator/slots.py:396-411`), which is value-side forgery. Prose-side forgery is uncovered: the
fill LLM writes node bodies freely, and could emit a mutated sentinel, an extra sentinel, a
sentinel in a node that declared none, or drop one entirely. A dropped sentinel degrades quietly
(the reader just sees generic text). An **extra or mutated** sentinel is the real risk: it is an
unreviewed substitution point in prose a human approved believing it was static.

### 3.2 The check

A new deterministic post-fill check, in the same spirit as the four fail-closed post-conditions
`render_bound_skeleton` already carries (`binding.py:578-586`). Given the contract's declared
personalizable slots and the filled blob, assert:

- The multiset of well-formed sentinels in the blob **exactly equals** the declared multiset,
  per node, not just per document. Per-node matters: a sentinel that migrated from node A to node
  B changes what a reader sees where.
- No sentinel-shaped-but-malformed string appears anywhere in the blob (a near-miss is a stronger
  signal of a problem than a clean absence).
- Each sentinel's wrapped text equals its slot's `generic_default` exactly. The LLM must not have
  "improved" the placeholder.

Fail closed: a blob failing this check is discarded exactly as a schema-invalid or
gate-failing repair candidate is today (`src/cyo_adventure/moderation/repair.py:7-13`). It must
run **before** the blob can reach the human approval queue, so the artifact a guardian approves is
the artifact that passed.

Where it hooks in: alongside the existing gate call in `generation/worker.py` (see the
`render_bound_skeleton` call at `worker.py:898` and the post-condition handling at `:867` and
`:1601`) and in `generation/import_story.py:352`, which is the second `render_bound_skeleton`
caller and the path the `cyo-author` skill uses.

### 3.3 Rescreen and repair interaction

`moderation/rescreen.py` re-reads published blobs and re-runs classifiers over them
(`src/cyo_adventure/api/rescreen.py:1-8`). Sentinels will be present in that text. Two decisions
to make explicitly rather than by accident: whether the classifier sees the sentinel markers or
the stripped generic text (recommendation: **stripped**, so classifier scores are comparable
across the migration boundary and no classifier sees a token it has no training for), and whether
a rescreen that rewrites nothing can still fail sentinel integrity (recommendation: **yes**, as a
detection signal for corruption at rest).

`moderation/repair.py::attempt_repair` re-prompts the generator to revise prose. Sentinels must be
added to its preserve-list, and the P2 check must re-run on the repaired blob, since
`moderation/pipeline.py` already re-validates and re-gates a repair candidate before adopting it.

## 4. Phase 3: leak-surface guard points

Each of these is a concrete place where a sentinel token or a real value could escape. The
architecture makes the **real value** case structurally impossible server-side; these guards are
about the **sentinel** case (an ugly token reaching an external provider or a kid-facing list) and
about defense in depth.

| Surface | File | Current behaviour | Guard to add |
|---|---|---|---|
| Cover-art prompt | `src/cyo_adventure/covers/prompt.py:87-111` | Embeds blob `title`, a protagonist name, and a 240-char opening excerpt (`_opening_excerpt`, `:19-40`) and ships them to an external image provider | Strip sentinels to their generic default before building the prompt. Assert in test that no sentinel marker can appear in a built prompt |
| Recommendation payloads | `src/cyo_adventure/api/recommendations.py:79-94`, `:347` | Surfaces `blob["title"]` as the item title and `rater.display_name` as `recommender_name` | Strip sentinels from the title. Note: `recommender_name` is a separate, already-sanctioned disclosure (ADR-016, and PR #415's B6 decision); do not conflate the two |
| Reading history | `src/cyo_adventure/api/reading_history.py:89`, `:323` | Its own `_book_title` helper, duplicated from recommendations by convention | Same strip. Because the helper is deliberately duplicated, the strip must be applied in both places or extracted to one shared helper |
| Library lists | `src/cyo_adventure/api/library.py` | Serves per-profile shelves | Same strip on any title field |
| Moderation and rescreen re-reads | `src/cyo_adventure/moderation/rescreen.py`, `moderation/classifiers.py` | Re-run classifiers over stored prose | Strip before classification (see 3.3) |
| Pipeline event log | `src/cyo_adventure/events/writer.py:17-19` and the `_PAYLOAD_ALLOWLIST` below it | Per-event-type key allowlist enforcing the PII-free payload contract | Add new event types for consent grant, consent revoke, and toggle flip, each with a keys-only allowlist entry (`slot_type`, `ring`, `action`, and at ring 2 `connected_family_id`). **No values, ever.** The allowlist mechanism already prevents this if the new entries are written correctly |
| Notification payloads | `src/cyo_adventure/api/notifications.py:121-133` | Serializes `title` and `body` free text on a guardian-only feed | Strip sentinels. The feed is guardian-only and gated before any query runs (`notifications.py:104-116`), so the risk is cosmetic rather than a boundary crossing, but an unresolved token in a notification is a visible defect |
| Text-to-speech | `frontend/src/reader/useReadAloud.ts:34-99` | Uses the browser `window.speechSynthesis` API on already-substituted text | Not a server guard. Record in the privacy model that on platforms with cloud-backed voices, a personalized passage read aloud may leave the device through a path the app does not control. Consider surfacing this in the guardian consent copy |
| Save-state export and sync | `frontend/src/player/types.ts:71` (`ReadingState`) | Carries node ids and variable state only | **Already safe.** No change; add a regression test so it stays that way |
| Ring-3 aggregates | Unbuilt (ADR-016 `:152-155`) | N/A | Forward-binding constraint: when ring-3 aggregation is built, it must render fully generic. Land this as a test in that workstream, not only as a sentence in ADR-023 |

Implementation note: prefer **one shared strip helper** applied at the serialization boundary over
per-call-site strips. A per-call-site approach is exactly the pattern that gets forgotten on the
29th router.

## 5. Phase 4: data model

### 5.1 Per-profile toggles

On `child_profile` (`src/cyo_adventure/db/models.py:398`), following the existing pattern of
boolean guardian controls on that table (`tts_enabled:445`, `reduce_motion:449`):

- `real_name_ring1_enabled: bool`, default `False`
- `real_name_ring2_enabled: bool`, default `False`
- Per-slot-type enablement for the remaining taxonomy entries. Prefer a single JSONB
  `personalization_slots` column with an api-layer-validated shape over 8 or more boolean columns,
  matching how `allowed_content_flags` is handled (`models.py:434-436`, with the
  api-layer-is-the-only-writer discipline documented at `:425-433`). A CHECK constraint cannot
  express the shape; the API layer must be the sole writer, as it already is for that column.

Migration via Supabase CLI SQL under `supabase/migrations/` (ADR-012), not Alembic.

### 5.2 Ring-2 disclosure consent

A new table rather than columns, because consent is per profile **and** per connection **and** per
slot type, so it is not a single fact about a profile:

- `profile_id`, `connected_family_id` (FK to the `family_connection` counterparty), `slot_type`
- `consent_accepted_at`, `consent_policy_version`, `consent_signer_name`, `consent_ip`

Mirror the CHECK-enforced pairing already used on `User`
(`models.py:305-308`: the four consent columns are all-null or all-populated together, enforced by
`CheckConstraint`). That pairing is what makes the record evidentiary rather than decorative;
copy it exactly.

Cascade rules: `ON DELETE CASCADE` from both the profile and the family connection. Revoking a
`family_connection` must invalidate the consent, not orphan it. This matters for the deletion
drill (`tests/integration/test_deletion_drill.py`) and for ADR-018's erasure obligations.

### 5.3 Eligibility flags

Per storybook version (or per generation job, whichever the schema makes cheaper to query
alongside the blob):

- `personalization_eligible: bool` (does this story carry personalizable sentinels at all)
- `pronoun_parameterized: bool` (a **separate** flag, per ADR-023 section 5, off by default and
  set only by an explicit per-skeleton audit)
- The declared sentinel manifest, so the P2 check has something authoritative to compare against
  at rescreen time without re-reading the contract from disk

### 5.4 The client-held values payload

Shape (illustrative, not final):

```text
{
  profile_id: string,
  policy_version: string,
  resolved_at: timestamp,
  ring: 1 | 2,
  values: { <slot_type>: string }
}
```

Rules the payload must obey:

- Fetched per profile, **never embedded in a story response**. Keeping the two responses separate
  is what preserves the `id@version` cache key.
- Small and bounded. It carries at most one short string per included taxonomy entry.
- Stored in its own IndexedDB store, keyed by `profile_id`, so a single-key delete revokes it.
  Do **not** put it in the `storybooks` store, which is deliberately device-wide and
  profile-independent (`frontend/src/offline/db.ts:17-21`).
- Every value passes the structural checks and band-mandatory denylist floor from
  `validator/slots.py` **server-side when the payload is built**, and the client falls back to the
  generic default rather than rendering anything that arrives malformed. See risk R4.

## 6. Phase 5: client-side resolution

### 6.1 Where it lives

`frontend/src/player/`, next to the existing engine (`engine.ts`, `evaluator.ts`, `machine.ts`,
`series.ts`, `types.ts`). That directory already exists to mirror backend logic on the client and
already carries the test discipline this needs. A new `personalization.ts` plus
`personalization.test.ts` fits the established shape.

The resolver is a pure function: `(text: string, values: ValuesPayload | null) => string`. Given
`null` or a missing key it returns the generic default. It must be pure, total, and synchronous,
so it can be called from render without a loading state and so a missing payload degrades to the
generic experience rather than to an error.

### 6.2 Where it is applied

`frontend/src/reader/Reader.tsx` renders node bodies through `<PassageText text={node?.body ?? ''} />`
(`Reader.tsx:365`, `:419`) and passes body plus choice labels to read-aloud (`:96`, `:151`).
Substitution is applied at those render sites, and to choice labels and ending titles, and nowhere
else.

Deliberately **not** substituted: the admin review surfaces. `PassageText` is also used by
`frontend/src/admin/ReviewDetailPage.tsx` and `frontend/src/admin/ReviewCompare.tsx`. An admin
reviews the generic artifact, which is the artifact that was approved and stored. Do not wire the
resolver into those call sites.

### 6.3 Offline and revocation mechanics

- **The story cache is untouched.** `cacheStorybook` keys by `` `${story.id}@${story.version}` ``
  (`frontend/src/offline/db.ts:161-163`). Because the blob is identical for every reader, this
  stays correct and siblings keep sharing one entry. This is the payoff of the whole architecture;
  do not undo it by adding a profile dimension to that key.
- **A new store** for values payloads, added as a `DB_VERSION` bump in the `upgrade` callback
  (`db.ts:92-116`), following the existing `if (oldVersion < N)` pattern. Note the existing
  `blocking` / `blocked` / `terminated` handling (`db.ts:117-136`) exists because a version bump
  can hang every tab; a bump is not free and should carry its own test, as the current ones do.
- **Purge triggers.** Delete the values payload on: toggle flip to off, ring-2 connection
  revocation, profile deactivation, guardian sign-out and device handover (alongside the existing
  `clearReadingStates`, `db.ts:198-201`), and consent policy-version change. Add these to
  `frontend/src/offline/revocation.ts` next to `reconcileOfflineCache` (`:85`), but keep them
  separate from it: that function's `#CRITICAL` contract is that it runs **only** after a
  successful authoritative library fetch (`revocation.ts:39-52`), and a values purge has different
  and looser preconditions. Do not overload it.
- **The honest limit.** A device offline at the moment of revocation keeps its payload until it
  next opens the app. `revocation.ts:16-25` already documents an analogous mid-read gap for book
  revocation. Document this one the same way, in code, and make sure the guardian-facing copy says
  "new readings" rather than implying retroactive erasure.

### 6.4 Kid-visible indicator and one-way veto

Every personalized book carries a visible, age-appropriate indicator that it uses the child's own
details, and a control to turn it off. The veto is **one-way**: a child can turn substitution off,
never on. The asymmetry is deliberate and the pronoun case is why. A child who is uncomfortable
seeing a pronoun in their book must be able to stop it without asking an adult; a child must never
be able to enable a disclosure a guardian did not consent to.

Implementation notes: the off state is per profile per device and persists locally. It does not
change the server-side toggle (a guardian's consent is unchanged by a child's local preference) and
it does not require a network call, so it works offline. It should read as a preference, not as a
warning: "Use my name in stories" with an on/off, not "This book contains your personal data."

## 7. Phase 6: guardian surfaces

- Toggle UI in the guardian profile editor (`frontend/src/guardian/`, alongside the existing
  profile management), default off, with the ADR-023 section 8 framing: the fictional-protagonist
  experience is the recommended default, and real-name substitution is an escalation on top of it.
- Ring-2 consent capture reuses the shape of `GuardianConsentPage.tsx` (built for ADR-018 D1) but
  is a **separate flow with separately-worded copy**, not a reuse of that page's consent record.
  ADR-023 OD-1 gates whether this ships at all.
- The consent copy must state, in plain language: which slots, which ring, that revocation is
  prospective, and that the value never leaves the family's devices in story content form.

## 8. Phase 7: catalog migration

Per ADR-023 section 6: existing catalog content is test and development material with no live
child-linked production data, so there is no backward-compatibility obligation.

- **Replace by default.** Regenerate stories onto the new sentinel-tagged standard. The volume is
  small (61 skeletons, 45 with contracts) and it is test content.
- **Repair only where a specific story is expensive to reproduce.** Repair here means a
  purpose-built reprocessing pass, not `moderation/repair.py::attempt_repair`, which is a narrow
  soft-gate re-prompt that "only produces the candidate revision; it does not decide whether to
  adopt it" (`repair.py:5-6`). Reusing its shape is a deliberate build, not a reuse.
- Any story not migrated is simply `personalization_eligible = false` and renders exactly as it
  does today. There is no forced migration deadline.
- **Pronoun audit is separate and per skeleton.** Gendered pronouns are hardcoded in beats guidance
  and choice labels: `skeletons/10-13/the-cinderwick-exchange.json:89` ("she tells {HERO} the
  escapement is worn"), `skeletons/10-13/the-envoy-of-three-courts.json:135` ("See {COURIER} on his
  way and snatch some sleep"), `:331`, `:582`, `:760`, `:862`. Every node body in the catalog is a
  `<<FILL ...>>` directive, so this is an audit of authoring directives, not of stored prose. A
  skeleton gets `pronoun_parameterized = true` only after someone has read its directives and
  confirmed a pronoun swap produces coherent text.

## 9. Phase 8: copy and compliance artifacts

- **Route A messaging addendum.** `src/cyo_adventure/story_requests/interpretation.py:1017-1035`
  currently registers the absolute "Heroes in our stories always have made-up names" for young,
  middle, and teen bands. It must be reworded before any toggle ships, so the absolute claim is
  never live alongside a feature that contradicts it. The claim that survives is about egress and
  storage, not about what appears on a screen. Coordinate the exact wording with PR #415's A11 copy
  (ADR-023 coordination section) so one sentence is true in both surfaces.
- **Compliance plan caveat.** A small proposed note against the Route A record in
  `docs/compliance/coppa-gdpr-remediation-plan.md` Section 5 "Self-naming" (`:725-759`), flagging
  that render-time substitution softens the messaging claim without changing the egress claim.
- **Privacy model.** New entry for the client-held values payload as a child-linked data category
  that never reaches the server in content form, plus the TTS note from section 4.
- **ADR-018 / P7-08.** This feature is a new processing purpose. It adds no new provider
  counterparty, which is the good news, but it changes what the privacy notice and the App Store
  data classification must say.
- **ADR-016 amendment.** One edit, not two. See ADR-023's coordination section: PR #415's B6 wants
  a sentence recording ring-2 attribution granularity; this feature wants ring-2 personalization
  granularity recorded alongside it. Whoever writes it writes both.

## 10. Risk register

| ID | Risk | Severity | Mitigation | Phase |
|---|---|---|---|---|
| **R1** | **Sentinel forgery in prose.** The fill LLM emits an extra, mutated, or relocated sentinel; a human approves a blob containing an unreviewed substitution point | High | The P2 exact-multiset, per-node integrity check, fail-closed, run before the approval queue and again after any repair | P2 |
| **R2** | **A guard point is missed on a new surface.** The 29th router serializes a blob title without stripping | High | One shared strip helper at the serialization boundary, not per-call-site strips; a test that enumerates title-bearing response models | P3 |
| **R3** | **Offline cache poisoning across siblings.** A future change adds a profile dimension to the story response and the shared `id@version` key starts serving one sibling's copy to another | High | The architecture prevents it, but nothing enforces it. Add a test asserting the story response is byte-identical for two profiles with different toggle states | P5 |
| **R4** | **`display_name` is under-validated for this use.** It is length-bounded free text only (`api/schemas.py:1032-1034`), written straight to the row (`api/profiles.py:102-103`, `:286`), while sibling fields that reach a prompt are far stricter (`PinCode` at `:1038`, banned themes at `:1050-1051`) | High | Apply `validator/slots.py` structural checks plus the band-mandatory denylist floor **twice**: when the guardian sets the name, and again at render time. The second check is not redundant: names set before this feature shipped were never checked | P4, P5 |
| **R5** | **Revocation residue.** A device retains a synced values payload after a toggle flip or connection revocation | Medium | Purge on flip, revoke, deactivation, sign-out, and policy-version change. Document the offline-device window in code and keep guardian copy prospective | P5 |
| **R6** | **Ring-2 disclosure exceeds what the connection consented to.** A guardian who consented to recommendation attribution finds their child's name throughout another household's story prose | High | Separate, separately-worded consent event per profile, per slot type, per connection (ADR-023 OD-1). If OD-1 resolves against a separate consent, ring 2 must still be gated behind explicit, specific copy rather than inherited consent | P4, P6 |
| **R7** | **Pronoun outing at ring 2.** A pronoun disclosure reveals something about a child to extended family that the guardian did not intend | High | Pronouns are ring 1 only, hard-coded, with no toggle to raise them; plus the kid-visible one-way veto | P4, P6 |
| **R8** | **English-only morphology produces bad prose.** "a Maya", possessive edge cases, and verb agreement break substituted sentences | Medium | v1 is English only and scoped to she/her and he/him (agreement-identical pairs). they/them is deferred because singular "they" changes verb conjugation ("she runs" vs "they run"), which a token swap cannot retrofit onto already-conjugated stored prose. Prefer name slots in dialogue and ending titles | P1, P7 |
| **R9** | **Two rendering implementations drift.** The client resolver and any server-side stripping helper disagree about what a sentinel is | Medium | One canonical sentinel definition; the frontend imports it from a generated or checked-in shared constant rather than re-deriving the regex. Note the API client is generated from OpenAPI and CI fails on drift, so a schema-carried constant is the cheapest enforcement | P1, P3, P5 |
| **R10** | **Consent records leak values into the event log.** A well-meaning contributor adds the substituted name to a consent event payload for debuggability | Medium | The `_PAYLOAD_ALLOWLIST` mechanism in `events/writer.py:17-19` already rejects unlisted keys. Write the new entries with keys only, and add a test asserting a value-bearing key is rejected | P3, P4 |
| **R11** | **A real name lands in an antagonist or comic-mishap role.** A sibling name (taxonomy #3) is bound to a `COMPANION`-style slot that the skeleton later treats badly | Medium | Role-safety metadata on the slot: a personalizable slot mapped to a real-person field must declare that its role is never antagonist and never the subject of a mishap beat. Audit per skeleton, alongside the pronoun audit | P1, P7 |
| **R12** | **Sentinels reach a rescreen classifier as unfamiliar tokens** and shift scores relative to the pre-migration baseline | Low | Strip to generic default before classification (section 3.3), so scores stay comparable | P3 |
| **R13** | **The ADR-016 amendment gets written twice, racing.** This workstream and PR #415's B6 residual both edit the same document | Low | Single owner, single edit, covering both asks. Named explicitly in ADR-023's coordination section | P8 |

## 11. Open questions this plan cannot answer

These need decisions from outside the implementation:

1. **ADR-023 OD-1 through OD-4.** Ring-2 consent model, pronoun scope, Route A copy wording, and
   whether ring 2 is in v1 at all. OD-4 in particular could cut Phase 4's consent table and half of
   Phase 6.
2. **PR #415 A11 shuffle semantics.** Whether the shuffle changes what is stored or generated, or
   is purely a cosmetic client-side choice among generic names. If it changes the stored bound
   value, it touches the same slot the personalization sentinel occupies and P1 must be sequenced
   against it. The plan currently lists this as an open user-testing question, not a decision.
3. **Whether pronouns need a new profile field at all.** Deriving them from an existing attribute
   may not be possible without an inference this app has deliberately avoided making. If a new
   field is required, it is new child-data collection and needs its own justification in the
   privacy model, separate from the disclosure question.
4. **The exact sentinel delimiter.** Deliberately left open in section 2.3; it is a small decision
   that should be made once, in code, by whoever writes the check in P2.

## 12. Related

- [ADR-023](./adr/adr-023-story-personalization-slots.md): the decision record this plan
  implements, including the closed slot taxonomy and the parallel-workstream coordination asks.
- [ADR-016](./adr/adr-016-recommendation-sharing-social-boundary.md): the three rings and the
  ring-3 exclusion this feature inherits.
- [ADR-018](./adr/adr-018-childrens-privacy-compliance.md): the consent-event pattern and P7-08.
- [ADR-019](./adr/adr-019-parameterized-skeletons-theme-contracts.md): the slot machinery P1
  extends.
- [ADR-012](./adr/adr-012-supabase-cli-migrations.md): migrations are Supabase CLI SQL, not
  Alembic.
- [coppa-gdpr-remediation-plan.md](../compliance/coppa-gdpr-remediation-plan.md): Section 2 bullet
  3 and Section 5 "Self-naming" (Route A), and the proposed messaging caveat P8 adds.
- [privacy-model.md](./privacy-model.md): needs the values-payload and TTS entries.
- [capability-register.md](./capability-register.md): needs new G-series and K-series IDs before
  P1 starts.
