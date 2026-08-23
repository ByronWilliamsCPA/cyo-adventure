---
title: "ADR-023: Guardian opt-in story personalization (render-time slot substitution)"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the design for guardian opt-in personalization: stories are always generated,
  moderated, and stored with generic sentinel placeholders, and a small per-profile values
  payload is resolved CLIENT-SIDE at render time so a real child detail can appear in a book
  without ever reaching a provider or being persisted in story content. Fixes the closed slot
  taxonomy (what may and may not be substituted), the ring ceilings and consent model, the
  per-story eligibility marker, and the migration posture for existing test content."
tags:
  - planning
  - architecture
  - decisions
  - privacy
  - safety
  - generation
---

# ADR-023: Guardian opt-in story personalization (render-time slot substitution)

> **Status**: Accepted (2026-07-29). **Every owner-level open decision is closed** (the 3-5
> band question and OD-1 through OD-5, confirmed by owner choice on 2026-07-25 and recorded
> in the Validation section below). The counsel gate that kept this ADR at Proposed was closed
> by owner review on 2026-07-29: the project has no external counsel, so the owner's review is
> the operative sign-off at this deployment scale. OD-1 closed conservatively (separate
> disclosure consent confirmed); OD-5 closed conditionally (self-verification accepted for R1,
> immediate-family deployment only, with mandatory reassessment at every deployment-phase
> boundary and a hard revisit before iOS/TestFlight or any commercial availability; see the
> OD-5 closure record and the regulatory classification note in the Validation section).
> Acceptance at R1 scope is not acceptance at commercial scope.
> **Date**: 2026-07-25
> **Relates to**: [ADR-016](./adr-016-recommendation-sharing-social-boundary.md) (the three
> rings this feature's ceilings are cut from), [ADR-018](./adr-018-childrens-privacy-compliance.md)
> (the consent-event pattern and the open D1-D4 compliance decisions), [ADR-011](./adr-011-story-scale-framework.md)
> (the frozen constraint grammar personalization must vary strictly inside),
> [ADR-019](./adr-019-parameterized-skeletons-theme-contracts.md) (the theme-contract slot
> machinery this reuses and extends), [ADR-005](./adr-005-mandatory-human-approval.md) (human
> approval still gates the generic blob), [coppa-gdpr-remediation-plan.md](../../compliance/coppa-gdpr-remediation-plan.md)
> (Section 2 bullet 3 and Section 5 "Self-naming", the Route A ruling)
> **Source**: design conversation 2026-07-25; no code exists for this feature yet

## TL;DR

Stories stay generic everywhere the system can see them. Generation, the deterministic
validator gate, moderation, cover art, recommendations, the pipeline event log, and the stored
`storybook_version.blob` all continue to hold nothing but generic placeholder text, forever and
for every reader. A guardian may opt in, per child profile, to have a small, closed set of those
placeholders replaced with that child's real details, and that replacement happens only in the
browser, at render time, from a per-profile values payload the server never bakes into content.
The result: a child can read a book that says their own name, while the invariant "a real child's
name never reaches a provider" stays exactly as true as it is today. Ring 1 (own family) is the
default ceiling; ring 2 (a connected family) is allowed for a subset of slots and requires its own
separate disclosure consent; ring 3 is categorically excluded and always renders generic.

Two things this does **not** claim, stated up front because both are easy to over-read. At ring 2 a
child's details **do leave their household**, rendered on a connected family's devices; the claim
that survives is about providers and stored content, not about staying inside one home. And
substituted text is read aloud through the browser's `speechSynthesis` API, which on several
platforms is cloud-backed, so a personalized passage may leave the device by a path the app does
not control (see the leak-surface register in the implementation plan).

## Context

### Problem

The pipeline's current posture on child identity is absolute and deliberately so. A concept
brief's `protagonist.name` is guardian-authored fiction, explicitly decoupled from any real
child (`src/cyo_adventure/generation/concept.py:8-17`, `:143-149`), and the brief derivation
falls back to a literal `"Explorer"` with the comment "Generic fictional protagonist; NEVER a
real child's display name" (`src/cyo_adventure/story_requests/brief.py:79-81`). The PII egress
guard is described in its own module docstring as "the sole chokepoint that prevents real-child
identifying data from reaching an external LLM provider"
(`src/cyo_adventure/generation/pii.py:3-5`). A child who asks to be the hero is hard-blocked at
request-interpretation time as `SET_ASIDE` / `IDENTITY_PROTECTION`
(`src/cyo_adventure/story_requests/interpretation.py:552-556`), with the kid-facing line
"Heroes in our stories always have made-up names, so we chose one for this adventure!"
(`interpretation.py:1025`).

That posture is right, and it is also the product's single largest experiential gap against
personalized-story competitors. The remediation plan already anticipated this exact tension: it
records Route A (disallow self-naming) as the resolved default and Route B (allow self-naming)
as the rejected alternative whose cost is that "the real name would then be sent to every
text/image provider in scope and *persisted* in the finished story content itself
(`storybook_version.blob`)"
(`docs/compliance/coppa-gdpr-remediation-plan.md:746-749`), which "would need its own explicit
lawful basis and specific notice/consent language" (`:750-753`). It closes with "Route B remains
available later as a deliberate, separately scoped feature decision if the product calls for it"
(`:757-759`).

This ADR is not Route B. It is a third route the remediation plan did not consider: keep the
generic story as the only artifact that ever exists server-side, and personalize at the last
possible moment, on the child's own device, from data that never leaves the family's own trust
boundary in content form. Every cost the plan attributes to Route B (provider egress, persisted
PII in the blob, an extended retention and export surface, a raised DPIA rating) is avoided by
construction rather than by policy.

### Constraints

- **The egress invariant is not negotiable.** `assert_prompt_pii_safe` must remain the sole
  chokepoint with no carve-out. Any design that adds "except this one intentional case" to that
  guard is rejected on its face; the remediation plan already names that as Route B's core
  defect (`coppa-gdpr-remediation-plan.md:742-745`).
- **Ring 3 is closed.** ADR-016 requires that "no child identity, family identity, or
  connection-graph information may surface in or be inferable from a global recommendation"
  (ADR-016, "Ring 3: global (system only, future)") and treats anonymization as "a hard
  requirement, not an optimization" (ADR-016, "Trade-offs"). Anything visible outside rings 1 and 2
  renders fully generic, without a toggle to change that.
- **The offline cache is device-wide, not per-reader.** `frontend/src/offline/db.ts:161` keys
  cached story blobs by `` `${story.id}@${story.version}` `` only, and the store's own docstring
  explains why: "`storybooks` is keyed by `id@version` only, not by profile, because a book can
  be legitimately assigned to more than one sibling profile on the same device"
  (`db.ts:17-21`, restated at `frontend/src/offline/revocation.ts:64-69`). Any server-side
  per-reader name resolution would break this: sibling B's device would serve sibling A's
  substituted copy out of a shared cache entry.
- **Human approval still gates everything.** ADR-005's guardian gate reviews the generic blob.
  Personalization must not create a surface a human never reviewed.
- **English only in v1.** Possessive formation, article selection, and verb agreement are all
  English-specific; a token-swap mechanism cannot be assumed to port.

### Significance

This is the first feature in the product that deliberately puts a real child's personal detail
into rendered story content. Getting the boundary in the right place, at the render step rather
than the generation step, is what makes it a small, auditable change instead of a redesign of
the privacy architecture. Getting the taxonomy right, above all the exclusions, is what keeps it
from becoming an open-ended child-data collection surface with a story-shaped justification.

## Decision

**We will add guardian opt-in, per-child-profile personalization implemented as client-side,
render-time substitution over generic sentinels that the server always stores and always serves
unchanged.**

### 1. Architecture: the server never personalizes

The stored blob contains sentinel tokens (a generic default rendered verbatim into the fill
output, see section 2). The server serves that blob byte-identically to every caller, regardless
of viewer, ring, or toggle state. A separate, small per-profile "personalization values" payload
is fetched alongside it and resolved in the reader.

This single choice resolves four problems at once, and it is the reason to prefer it over any
server-side alternative:

- **Cache-key collision**: the content is unchanged, so `id@version` remains a correct cache key
  and sibling profiles keep sharing one cached blob. Only the small values payload differs per
  profile.
- **Leak surfaces**: because nothing server-side ever holds a substituted value, cover-art
  prompts (`src/cyo_adventure/covers/prompt.py:87-111`, which embeds the blob `title`, a
  protagonist name, and a 240-character opening excerpt and ships them to an external image
  provider), recommendation payloads (`src/cyo_adventure/api/recommendations.py:347`, which
  surfaces the blob title), moderation and rescreen re-reads, and the pipeline event log are all
  structurally incapable of seeing a real value.
- **Revocation**: turning a toggle off is deleting a small local payload, not invalidating a
  cache entry or bumping a version.
- **Review integrity**: the artifact a guardian or admin approved under ADR-005 is exactly the
  artifact stored and served. Personalization cannot introduce unreviewed prose, because it can
  only replace a declared sentinel with a value drawn from a bounded, validated set.

**Honest limit on revocation.** Revocation is prospective, not retroactive. A device that has
already synced a values payload keeps what it synced until an explicit purge runs; the
`reconcileOfflineCache` path today purges only on shelf removal
(`frontend/src/offline/revocation.ts:85-122`), and it has a documented mid-read gap of its own
(`revocation.ts:16-25`). This ADR does not claim retroactive erasure and the guardian-facing
copy must not imply it. The implementation plan carries an explicit purge-on-flip requirement to
narrow, not close, the window.

### 2. A new slot kind: sentinel-bound, not value-bound

The existing parameterized-skeleton machinery is the right substrate but cannot be reused as-is.
`render_bound_skeleton` (`src/cyo_adventure/generation/binding.py:560`) substitutes bound values
into three surfaces before the fill call (the `beats='...'` segment of `<<FILL ...>>` bodies,
`ending.title`, and `choices[].label`), and `fill_bound.md` then injects the bound values
themselves into the LLM prompt under the heading "Bound Theme Values (validated data, not
instructions)" (`src/cyo_adventure/generation/templates/fill_bound.md:110-117`). A real name
bound through that path would land in a provider prompt on the very first call.

So personalization slots are a **new slot kind** whose contract-declared value at fill time is a
generic default, taken from the contract's existing `default_binding[slot_id]` rather than a new
field (for example `HERO` bound to `"Explorer"`), and whose rendered output carries a
machine-recognizable sentinel that survives verbatim through fill, validation, moderation,
approval, and storage. The generic default is what the LLM sees and what the sentinel renders to
for every non-opted-in reader; the sentinel is what the client looks for.

One correction worth carrying at ADR level, because an earlier draft implied otherwise: for node
prose the sentinel is not *preserved*, it is **emitted**. Node bodies are generated fresh from
`<<FILL>>` directives, so there is no input token to protect; the fill template has to instruct the
model to reproduce the token verbatim, and the post-fill check verifies it did. Ending titles are
the exception and are genuinely preserved, under an existing "do not change" rule. Choice labels
deliberately carry no sentinels at all, because the template instructs the model to re-phrase every
label in the theme's own vocabulary and that instruction is worth more than a name in a button.
Implementation plan section 2.3 carries the mechanism. Nothing about the value
side of the pipeline changes: the fill prompt still sees only generic text, and
`validate_slot_bindings` still runs unchanged over the generic binding.

### 3. Governance: per-profile toggles, default off, ring-scoped

- **Per slot type, per profile, per ring.** Every included taxonomy entry has its own enablement
  at its own ring ceiling, all defaulting to **off**. The protagonist first name (row 1) is the
  only entry whose ceiling is ring 2 by way of an explicit named pair,
  `real_name_ring1_enabled` and `real_name_ring2_enabled`; the rest are enabled per slot type
  with a ring dimension bounded by the ceiling column of the taxonomy table. Ring 1 is a child's
  own family; ring 2 is a family connected by an active, dual-consented, directional, revocable
  `family_connection` (ADR-016, "Ring 2: connected families (allowed, guardian-gated, the cousins case)").
- **The ring-2 consent rule, stated once (this closes an ambiguity a reviewer caught).** There is
  **one ring-2 disclosure consent record per (child profile, connection)**, and it covers every
  slot type that profile has opted into at ring 2. There is **no** per-slot-type consent record and
  **no** per-slot-type signature ceremony. Concretely: a guardian consents once for Alex with the
  Diaz family, and that single record carries the enumerated set of Alex's ring-2 slots it covers
  (first name, sibling reference, pet name, kinship label, favourites, home type, pet species, in
  whatever subset is enabled). The enumeration exists so the scope of a past disclosure is legible
  after the fact, not so each entry needs its own signature. **Widening** the set requires
  re-consent, which supersedes the record in place with a new timestamp and policy version;
  **narrowing** it does not, since it only shrinks the disclosure. One audit artifact per
  disclosure relationship.
- **One slot type carries an extra condition, and only one.** The sibling reference (taxonomy row
  3) discloses a second child's name, so at ring 2 it resolves only when the **referenced**
  profile's own ring-2 enablement and consent also cover that same connection. This is a predicate
  on the values fetch, not a second consent record: sibling B's guardian has already signed B's own
  ring-2 consent for that connection, and this condition simply reads it.
- **Ring 2 requires its own separately-worded disclosure consent**, timestamped and
  policy-versioned, mirroring the paired `consent_accepted_at` / `consent_policy_version` /
  `consent_signer_name` / `consent_ip` columns already CHECK-enforced on `User`
  (`src/cyo_adventure/db/models.py:305-308`, `:385-395`) for ADR-018 D1. It must **not** reuse
  the account-level onboarding consent, and it must **not** reuse the `family_connection`'s own
  `consented_by_sharer_user_id` (`db/models.py:532-535`), which consents to recommendations
  crossing the boundary, not to story content bearing a real child's details. The reasoning is
  that COPPA's 2025 amendments require disclosure consent to be obtained separately from
  collection consent; reusing one signature for both makes the disclosure unverifiable after the
  fact. This is a design position, not a legal conclusion, and is one of the two items flagged
  for counsel below.
- **Ring 3 has no toggle.** It is categorically excluded. Any surface visible beyond rings 1 and
  2, including any future ADR-016 ring-3 aggregate recommendation, always renders the generic
  sentinel default. There is no configuration that changes this.
- Consent and toggle changes are recorded as pipeline events that carry the fact of the change
  and never the values, matching the PII-free payload allowlist contract already enforced in
  `src/cyo_adventure/events/writer.py:17-19`.

#### 3a. How a value actually crosses to a connected family

The delivery mechanism, because "ring 2 is allowed" is not a design on its own. Ring 2 uses
**the same client-side resolution pattern as ring 1**, with one difference: the values payload is
fetched from a cross-family endpoint authorized by the connection rather than by the reader's own
family membership.

- The story blob is generic and identical for everyone, as always. Nothing about the artifact
  family B receives is Alex-specific.
- Family B's reader, on opening a book whose personalization subject is a profile outside its own
  family, requests that subject's ring-2 values from a new endpoint. The endpoint returns values
  only when **all three** conditions hold: an active dual-consented `family_connection` in the
  correct direction, the subject profile's ring-2 enablement for the requested slot types, and a
  ring-2 disclosure consent record covering that (profile, connection, slot type). Any one
  missing returns an empty payload, and the reader renders the generic default.
- Because the gate is on the **values fetch** and not on the book, a personalization-eligible book
  that reaches an unconnected family through the catalog renders fully generic with no additional
  enforcement. That is the structural property that makes ring 3 exclusion hold for **content**
  without a per-surface check. Do not over-read it: the *payload* path is a runtime predicate that
  somebody has to write, test, and keep correct (implementation plan 8.4). Content is free; the
  values route is not.

The implementation plan's section 8 designs this end to end: the endpoint, the authorization
predicate, the caller (which is not the reading child's own session directly, for reasons that
section works through), and a worked before-and-after user story.

**Prerequisite this ADR must name.** `Visibility` is a closed two-value enum, `family` or
`catalog` (`src/cyo_adventure/publishing/state_machine.py:45-55`), and
`recommendations.py::_visible_books` states plainly that "a cross-family (ring 2) book only ever
reaches this profile through the catalog + assignment path"
(`src/cyo_adventure/api/recommendations.py:135-137`). There is **no connection-scoped book
visibility today**: ring 2 currently carries recommendations, which are pointers, not books. So a
family-A book only reaches family B by being published to the catalog, where every family can see
it. This does not break the design (the values gate is what protects the content, not the book's
visibility), but it does mean ring-2 personalization's realistic v1 surface is a catalog book with
a personalization subject in a connected family, and that anyone else in the catalog sees the
generic version.

**Decision confirmed 2026-07-25 (owner choice, OD-4): the catalog surface is accepted for v1.**
Connection-scoped book visibility is explicitly **not** a prerequisite for this feature. The reason
this is safe rather than merely tolerable is that the gate sits on the values fetch and not on the
book, so the identical catalog artifact renders fully generic for every unconnected family with no
extra enforcement. If the product later wants "share this book with just the Diaz family", that is
a separate visibility feature standing on its own merits, not a debt this feature incurred.

### 4. Route A stays completely untouched at the request and generation layers

This is a load-bearing decision, not an omission. Because substitution happens at render time and
is decoupled from what was requested or generated, a child's self-naming request can still be
hard-blocked exactly as it is today: no change to
`src/cyo_adventure/story_requests/interpretation.py`, no change to `SELF_REFERENCE_LEXICON`
(`:179-186`), no change to the `ElementDisposition` / `ReasonCode` model, no change to the
`_ELEMENT_MUST_BE_NULL` invariant (`:262-271`). A family with the toggle on will still see their
child's name when reading, regardless of how the story was requested, because the toggle and the
request are independent.

Route A's protective mechanism is therefore fully preserved: a real name still never reaches a
provider, is still never persisted in the blob, and is still never echoed back through the
interpretation surface.

**Route A's messaging, however, needs a scoped addendum, and this ADR now carries the replacement
text.** The kid-facing copy at `interpretation.py:1019-1034` currently asserts an absolute
("Heroes in our stories always have made-up names"). Once render-time substitution ships, that
sentence is false for an opted-in family, and at ring 2 it is false on another household's devices
as well. The claim that stays true is about egress and storage, not about what appears on a screen.
Per OD-3 the copy is **drafted here rather than deferred**: the toggle-aware replacement pair is in
the coordination section's Ask 1b, and the mechanism that selects between the two variants is in
the implementation plan (section 12). The compliance plan carries
a proposed caveat note against the Route A record.

### 5. Eligibility is a per-story marker, not a global assumption

- For theme-contract-bound (parameterized) skeletons, name eligibility is whether the bound
  contract declares a `HERO`-equivalent identity slot. This is not universal: measured 2026-07-25, 45 of the
  catalog's 61 skeletons had a contract at all, and `HERO` was declared in 39 of those 45. The proportion
  moves as the catalog grows (current totals: [catalog-census.md](../catalog-census.md), `UW-G24`); the
  per-story eligibility rule does not.
- For the older non-parameterized `ConceptBrief` path, eligibility is a boolean set at generation
  time.
- **Pronoun eligibility is a separate per-skeleton flag from name eligibility**, and is off by
  default pending a per-skeleton audit. The catalog hardcodes gendered pronouns inside authoring
  directives that no slot binding can rewrite: `skeletons/10-13/the-cinderwick-exchange.json:89`
  has a beats segment reading "she tells {HERO} the escapement is worn", and
  `skeletons/10-13/the-envoy-of-three-courts.json:135` has the choice label "See {COURIER} on his
  way and snatch some sleep." A catalog-wide pronoun switch would produce incoherent prose.

### 6. Migration posture: repair or replace, with replace as the default

The current catalog is test and development content with no live child-linked production data, so
there is no backward-compatibility obligation. The team's intent, stated plainly: existing test
stories are either repaired (reprocessed onto the new sentinel-tagged standard) or replaced
(regenerated). **Replace by default**, given the low volume and the fact that it is test content;
repair only where a specific story is expensive to reproduce.

One clarification to prevent a false expectation: `moderation/repair.py::attempt_repair` is a
narrow, purpose-built soft-gate re-prompt that "only produces the candidate revision; it does not
decide whether to adopt it" (`src/cyo_adventure/moderation/repair.py:5-6`). It is not a migration
tool. Reusing its shape for a sentinel-tagging migration is a deliberate repurposing that has to
be built, not something available off the shelf.

### 7. The closed slot taxonomy

This is the central decision of this ADR. The list is **closed**: a slot type not on the include
list is excluded until a future amendment adds it, and "the guardian asked for it" is not a
sufficient reason to add one.

Two conventions used throughout: **profile-bound** means the value is selected from an existing
`child_profile` row in the requesting family, never free-typed, so there is no field into which a
third party's name can be entered. **Closed enum** means the value is chosen from a vocabulary
list shipped with the app, never free text.

#### Included

| # | Slot | Story value | Compliance category | Combination risk | Ring ceiling | Decision |
|---|---|---|---|---|---|---|
| 1 | Protagonist first name | Highest. The single detail that makes a book feel like the child's own. | Direct identifier (soft); already collected as `child_profile.display_name`, no new collection | Moderate. A first name alone is a weak identifier; it becomes materially riskier combined with a real location, which is why #9 is excluded | Ring 1 default; ring 2 with separate disclosure consent | **Include, profile-bound only** |
| 2 | Pronoun set (she/her, he/him only) | High for a child whose gender the default text gets wrong | Special-category-adjacent (gender); no new field if derived from an existing profile attribute, a new field otherwise | High at ring 2: pronoun disclosure can out a child to extended family in a way a first name does not | **Ring 1 only** | **Include, v1 scoped to she/her and he/him; they/them deferred** |
| 3 | Sibling or family-child name (a `COMPANION`-style slot) | High. A story with a real sibling in it is a distinct experience | Direct identifier for a *second* child who is not the subject of this book | Moderate at ring 2, and see the dual-consent rule below | Ring 1 + ring 2 | **Include, profile-bound to another `child_profile` in the same family. At ring 2, the referenced sibling's OWN ring-2 enablement and consent must also cover that connection** |
| 4a | Pet species | Moderate. Cheap warmth, near-zero identifier value | Not an identifier | Low | Ring 1 + ring 2 | **Include, closed enum only** |
| 4b | Pet name | Moderate | Weak identifier with credential-reset value | Real but ring-scoped: see the note below | Ring 1 + ring 2 | **Include, free text; never at ring 3, permanently** |
| 5 | Trusted-adult kinship label ("Grandma", "Abuela", "Auntie", "Grandpa") | High. Kinship vocabulary is culturally specific and cheap to get right | Not an identifier; a relationship label, not a person | Low | Ring 1 + ring 2 | **Include, closed enum only. A real adult's personal name is excluded: a third party who never consented** |
| 6 | Favorite color, food, hobby | Moderate. Small, frequent hits of recognition | Preference data, not identifying | Low, given a closed vocabulary | Ring 1 + ring 2 | **Include, closed vocabulary lists only, never free text** |
| 7 | Home type (house, apartment, farm, ...) | Low. Occasionally grounds an opening scene | Coarse, non-identifying | Low. Explicitly not a location: see #9 | Ring 1 + ring 2 | **Include, closed enum, low priority** |
| 8 | Dedication or inscription line | High emotional value, zero prose risk | Contains a name and a kinship label already covered by #1 and #5 | Low, because it is template-constrained | **Ring 1 only** | **Include, render-only over already-stored values: see the note below** |

#### Three ceiling decisions worth their reasoning

These three rows were argued both ways during review. The outcomes are recorded with the reasoning
so a later reader can contest the reasoning rather than guess at it.

**Rows 3 and 4b were raised from ring 1 to ring 1 + ring 2.** The original ring-1-only ceilings
were set against the wrong threat model, and correcting them also fixes a real inconsistency in
this ADR's own ring-2 argument.

- *Sibling name (row 3).* The objection to ring 2 was that it discloses a second child who is not
  the subject of this flow. That objection has force against a **third-party** child, which is why
  row 16 (friend name) stays excluded outright. It has much less force here: the sibling is the
  same guardian's child, so the same adult holds parental responsibility for both, and the consent
  is within their own authority rather than borrowed from someone who never gave it. **That
  authority is assumed, not verified**, though: the system infers it from two profiles sharing a
  family account, and this row is titled "sibling *or family-child*" precisely because it admits
  stepchildren, foster placements, and extended-family arrangements where the account-holding adult
  may not hold legal authority over the second child. So the ceremony adds an explicit
  parental-authority attestation for this case (implementation plan 10.1.1, item 3), and OD-5 flags
  the assumption for counsel rather than resting on it.

  The other residual risk is that sibling B might be personally more private than A, and the design
  answers that directly rather than by assertion: **at ring 2 the sibling slot resolves only if
  profile B's own ring-2 enablement and consent also cover that same connection.** B's name is
  governed by B's settings wherever it appears, including inside A's book.

  One framing caveat, recorded so it is not misused later. It is true that in the cousins case the
  connected household very likely already knows the sibling's name, and that observation is
  **residual-harm commentary only**: it bears on how much a disclosure costs, never on whether
  consent is needed. Consent is required regardless of what the recipient already knows. This
  sentence must never be cited as a reason to skip, bundle, or soften it.
- *Pet name (row 4b).* The objection was that pet names are classic security-question answers.
  Stated precisely for counsel, this is a **narrow-audience disclosure of a credential-adjacent
  datum**, and two distinct risks have to be separated because ring-scoping only touches one. The
  *disclosure* risk (who deliberately sees it) is genuinely small at ring 2: a parent-built,
  enumerable graph of typically one to three households who, in the cousins case, have met the dog.
  The *collection* risk (that a credential-adjacent value exists in our database at all, and in a
  breach corpus if we are breached) is **created at ring 1 and is entirely unchanged by this
  ceiling decision**. Raising the ceiling neither worsens it nor excuses it. So: defensible on
  disclosure grounds, while the collection question stands on its own and belongs in the DPIA's
  breach-impact analysis rather than here. What the credential concern still buys is permanent
  ring-3 exclusion and a length-bounded field rather than open text.
- *What this does to the ring-2 argument, and why that is a feature.* The coordination section
  below argues ring 2 needs stricter consent partly because a name arrives compounded with other
  details. Under the original taxonomy that argument was **false**: the richest compounding
  details were ring 1 only and could never co-occur. Raising rows 3 and 4b makes the argument true
  rather than shrinking the argument to fit. The ring-2 compounding set is now genuinely
  substantial (first name, a sibling's first name, a pet's name, a kinship label, favourites, home
  type, pet species), which strengthens rather than weakens the case for a separate, enumerated
  disclosure consent.

**Row 2 (pronouns) stays ring 1 only, deliberately.** With rows 3 and 4b raised, pronouns and the
dedication line (row 8, ring 1 only because a dedication is addressed to its own household) are the
only entries that do not reach ring 2, and pronouns are the only one held back on risk. The
reasoning that moved rows 3 and 4b does not transfer. A sibling's name and a pet's name are facts a
connected household in the cousins case very likely already knows; a child's pronouns may be
precisely what that household does *not* know, and the guardian consenting is not always the person
with standing to disclose it. The asymmetry is about marginal information and about whose fact it
is, not about squeamishness.

**Row 8 (dedication line) stays in v1, as a render-only feature.** This was reconsidered on the
grounds that a title-page overlay is a separate mechanism carrying its own validation and
revocation paths, and therefore poor value for a single decorative line. On inspection that premise
does not hold for this design. The dedication stores **no new kind of data**: its two parameters are
a name (already `child_profile.display_name`, row 1) and a kinship label (already a closed enum,
row 5), so it adds one `slot_type` row in a table that already exists, not a new store. It reuses
the same write-time validation, the same values payload, and the same purge triggers as every other
slot, so there is no second validation path and no second revocation path. The composed string is
never stored and never serialized by any API; it is assembled in the browser from values the reader
already holds. What is genuinely new is one small render component and one boolean. That is a low
enough marginal cost, against the highest emotional-value-per-line-of-code item in the taxonomy,
that deferring it would be a worse-engineered answer than building it. It is sequenced **last**
among the included slots, because it shares nothing with the sentinel work and can slip without
blocking anything.

#### Excluded

| # | Slot | Reason for exclusion |
|---|---|---|
| 9 | Real location of any kind: school name, street, landmark, sports team, any real specific place | A real name plus a real specific location is a materially higher child-safety (findability) risk than either alone. The narrative value is already served by a fictionalized or generic descriptor, so the risk buys nothing. Excluded as a whole class, not case by case |
| 10 | Surname | Converts a soft identifier (a first name) into a hard one, for negligible narrative gain |
| 11 | Exact age or birthdate | Reverses an existing, deliberate data-minimization decision. The app collects only a coarse age band, and `pii.py:16-20` records that a birthdate check was removed precisely because no caller could populate it |
| 12 | Physical appearance or descriptors | Near-zero prose value: the drafting guide already directs prose to "Address the reader as 'you,' never 'the protagonist' or a character name in body text" (`src/cyo_adventure/generation/templates/drafting_guide.md:105`), so there is no place in body prose where the reader-protagonist's appearance is described. The only surface where appearance would matter is cover art, which must never receive real child data |
| 13 | Disability or accessibility traits | Plot beats assume physical actions a token swap cannot make coherent. If representation is the goal, it belongs in the generation-time fictional `Protagonist.role` (`generation/concept.py:164-167`), not in this render-time mechanism |
| 14 | Holiday, cultural, or religious tradition as stored per-child profile data | Risks a GDPR Article 9 inference (religion) from a stored per-child field. The same outcome is already reachable without a new field, via story-request themes at generation time |
| 15 | Fears or phobias | Already handled by the existing G2 guardian-set controls: `banned_themes` and the content-flag caps (`db/models.py:437-444`, `story_requests/brief.py:87-124`). Not a render-time personalization field |
| 16 | Friend name (a non-family child) | Violates the family-only boundary outright, with no consent path for the friend or the friend's guardian |

### 8. The recommended default remains fictional, not personalized

`ConceptBrief.Protagonist` (`generation/concept.py:143-167`) already provides a guardian-chosen
fictional name and role, screened out of PII matching by design. That is the **recommended
default experience** and should be presented as such: a "no-consent middle tier" that delivers
most of the felt personalization ("Captain Rosa, a young explorer") with none of the disclosure.
Real-name substitution is an **opt-in escalation layered on top of it**, not a replacement for it,
and the guardian-facing UI should frame it that way rather than presenting the generic experience
as a degraded state.

### 9. Age bands: the child-facing half of this feature does not apply uniformly

**Decision confirmed 2026-07-25 (owner choice):** personalization **is** offered to the 3-5 band,
guardian-controlled, with no child-facing control rendered at that band. Confirmed as designed; no
change follows from the confirmation, and the reasoning below is now the recorded rationale rather
than a proposal.

The app spans six reading bands from 3-5 to 16+ (`storybook/models.py::AgeBand`, used throughout
`validator/band_profile.py`), and this feature assumes a child who can read the control it offers
them. That assumption fails at the bottom of the range.

- **3-5, and in practice much of 5-8**: the reader is pre-literate or barely literate. A
  child-facing "use my name in stories" control is not a meaningful consent surface for them: they
  cannot read it, and a tap on it carries no intent. For these bands, personalization is
  **entirely a guardian-controlled setting with no expectation of child-side agency**, and the
  child-facing control is **not rendered at all** rather than rendered and quietly ignored. Saying
  this explicitly matters: a veto nobody can exercise is worse than no veto, because it looks like
  a safeguard in a compliance review while providing none.
- **8-11 and above**: the child-facing control is rendered and is real. This is also where the
  pronoun slot matters most and where the ability to switch it off without asking an adult has
  actual value.
- Personalization is **not defaulted differently by band**: it is off everywhere. What varies by
  band is only whether a child-side control exists. There is no argument for auto-enabling it for
  young children on the theory that they will enjoy it more.
- The kinship-label slot (row 5) and the dedication line (row 8) are the entries with the most
  value at the youngest bands and the least risk, since neither is an identifier. If v1 needs to
  ship narrow, those two plus the first name at ring 1 are the defensible 3-5 subset.
- **At the other end of the range, the guardian may stop being the consent-holder.** This section
  assumes throughout that a guardian consents and a child does not. That holds under COPPA (under
  13) and under the US-only posture confirmed in ADR-018 D3. It does not hold universally: under
  GDPR Article 8 the member-state digital-consent age is 13 to 16, so a reader in the 13-16 or 16+
  band could be their own consent-holder rather than their guardian. That is shelved today with the
  remediation plan's Phase 9 (GDPR-K/AADC conformance), on the recorded basis that no UK/EEA users
  exist or are planned. If that fact changes, the 16+ band is where this feature's consent model
  breaks first, and it must be revisited together with ADR-018 D3 and Phase 9, not separately.

### 10. What a sentinel looks like to a human reviewer

Because the stored blob is what a guardian or admin approves under ADR-005, someone will read
marker-bearing prose during review. Two properties keep that acceptable, and they need stating
together because they sound contradictory otherwise.

A sentinel **wraps** its generic default rather than replacing it, so the underlying prose is
always complete and readable: with every marker stripped, the text reads exactly as an
unpersonalized story does. The reviewer is therefore reading real prose, not a template with
holes, and can judge it on its merits.

The review surfaces (`frontend/src/admin/ReviewDetailPage.tsx`, `ReviewCompare.tsx`) should
**render the markers visibly**, as a deliberate affordance rather than hiding them: a reviewer
approving a personalizable story ought to see exactly which words a family can replace, since that
is part of what they are approving. That is different from a **kid-facing** surface, where an
unresolved marker is a straightforward visual defect and must never appear. The rule is therefore
not "sentinels are always safe to display" but "sentinels degrade safely to correct prose
everywhere, and are shown deliberately in review and never in the reader".

### 11. Amendment (2026-08-07): the `character_name` slot (ADR-028 persistent characters)

> **This section is the authority on `character_name`.** It supersedes the earlier
> "Amendment (2026-08-06): the `character_name` personalization slot" section near the end of this
> document, which describes a shape the implementation did not take. ADR-028's `**Amends**` header
> points here.

ADR-028 introduces persistent reader characters (the `character` table). This amendment adds a
twelfth entry, `character_name`, to the closed taxonomy in section 7, with a structural property
none of the other eleven share.

- **Slot**: `character_name`, the persistent character's chosen name.
- **Ring ceiling**: ring 1 only, permanently, not a default open to a future ring-2 raise the way
  rows 3 and 4b were. A character name is unreviewed child free text (see the next bullet), and
  the three-ring boundary (ADR-018) keeps unreviewed child free text inside ring 1 only,
  categorically.
- **`REAL_PERSON_PERSONALIZATION_FIELDS` membership**: included, alongside the protagonist first
  name and the sibling name, because nothing stops a child naming a character after themselves or
  a real person.
- **Guardian toggle**: defaults off, like every other slot in this ADR. Enabling it never widens
  ring reach, since there is no ring-2 path for this slot to widen into.
- **Validation**: at set time, `PersonalizationSlotBody` and the database's
  `ck_cpp_value_cardinality` CHECK reject any value field on this slot type; at render time, an
  absent active character resolves to silent omission, the same generic-default fallback every
  other slot already uses, never a placeholder.
- **The property that sets it apart, and its three consequences.** Every other slot's value lives
  in the `child_profile_personalization` row itself; this slot's value is synthesized at render
  time from the profile's active `character.name`, so its row carries only the consent toggle.
  Three consequences follow directly.
  1. Turning the toggle off is the only way to clear the slot; blanking the character's name is
     not a clear, since the child can simply rename their character and the slot repopulates.
  2. Purging a profile's personalization must delete from `character` as well as from
     `child_profile_personalization`, or the purge silently leaves the child's chosen name in the
     database while reporting the slot purged (`PURGE_TARGETS`,
     `purge_profile_personalization()`, `src/cyo_adventure/api/personalization.py`).
  3. The exactly-one-value constraint (formerly `ck_cpp_exactly_one_value`, renamed
     `ck_cpp_value_cardinality`) had to become slot-scoped rather than a flat count of one, because
     this is the first slot type for which zero values is the correct shape, not a defect.

## Options Considered

### Option 1: Client-side render-time substitution over stored sentinels ✓

Chosen. The server holds and serves one generic artifact; the client resolves a small values
payload at render time. Preserves the egress invariant by construction, keeps the offline cache
key valid, keeps every server-side leak surface structurally clean, keeps the ADR-005 approval
artifact identical to the served artifact, and makes revocation a local delete.

### Option 2: Server-side per-reader resolution

Rejected. The server would substitute the reader's values into the blob before serving it. It is
simpler to reason about in a purely online, single-reader world and it centralizes the
substitution logic in one language instead of two. But it fails on four counts. It breaks the
`id@version` offline cache key, so a sibling on a shared device can be served another sibling's
substituted copy (`frontend/src/offline/db.ts:17-21`). It puts real values into the response path,
which means every cache layer, log line, and error report between the database and the device
becomes a potential leak surface. It makes the served artifact differ from the approved artifact.
And it makes ring enforcement a per-request authorization computation rather than a structural
property, which is exactly the kind of check that fails open under a future refactor.

### Option 3: Generation-time substitution (Route B)

Rejected, and already rejected once in `coppa-gdpr-remediation-plan.md:741-756`. Sends the real
name to every text and image provider, persists it in `storybook_version.blob`, and extends
retention, export, and deletion obligations to story content as PII-bearing data.

### Option 4: Do nothing; fictional protagonist names only

The status quo, and the honest baseline. It costs nothing and risks nothing. It is rejected only
because the fictional-name tier (Option "section 8" above) is being kept and strengthened as the
default anyway; this ADR adds an opt-in layer above it rather than replacing it, so the do-nothing
outcome is still what an untouched family gets.

## Consequences

### Positive

- ✅ A child can read a book that says their own name while "a real child's name never reaches a
  provider" remains literally true, with no carve-out added to `assert_prompt_pii_safe`.
- ✅ Every named leak surface (cover-art prompts, recommendation payloads, moderation and
  rescreen re-reads, the pipeline event log) is protected structurally rather than by a
  per-surface filter that a future contributor can forget to apply.
- ✅ Route A survives intact at the request and generation layers, so the self-naming block, its
  lexicon, and its disposition model need no change and no exception.
- ✅ The offline cache stays profile-independent and sibling-shared, so no cache redesign and no
  storage-footprint multiplication.
- ✅ The guardian-approved artifact and the served artifact remain byte-identical, so ADR-005's
  approval gate keeps meaning what it says.

### Trade-offs

- ⚠️ **Revocation is prospective, not retroactive.** A device that already synced a values payload
  retains it until an explicit purge. Mitigation: purge-on-flip, purge-on-connection-revoke, and
  purge-on-sign-out; the residual window is documented rather than papered over.
- ⚠️ **Two substitution implementations, or one shared one.** The reader already carries a
  client-side player engine that mirrors backend logic (`frontend/src/player/`). Personalization
  adds a second piece of rendering logic that must not drift. Mitigation: keep resolution in
  `frontend/src/player/` next to the existing engine and give it the same test discipline.
- ⚠️ **Ring 2 exports real child details into another household's devices**, and after the ceiling
  revision above that means a first name, a sibling's first name, a pet's name, a kinship label,
  favourites, and a home type, potentially all in one book. That is a genuinely new child-linked
  data flow, of a different order from ADR-016's existing recommendation attribution, and it is
  now a wider one than this ADR's first draft proposed. It is bounded by: a parent-built,
  enumerable, dual-consented graph; a separate enumerated disclosure consent per (profile,
  connection); and a per-referenced-child check so a sibling's name never rides out on their
  brother's consent alone. Confirmed as designed by the owner on 2026-07-25 (OD-5); it remains the
  item most in need of counsel sign-off.
- ⚠️ **A second adult now has to be right about a third person's privacy.** The sibling slot means
  guardian G's decision about child A's book discloses child B. The design answers this by reading
  B's own settings, but B is still a child whose preferences may not be recorded anywhere, and the
  guardian remains the only actual decision-maker. This is inherent to parental consent, not a bug
  in the mechanism, but it should not be described as if B consented.
- ⚠️ **`display_name` is under-validated for this use.** It is guardian free text with a length
  bound and nothing else: `DisplayName = Annotated[str, StringConstraints(strip_whitespace=True,
  min_length=1, max_length=120)]` (`src/cyo_adventure/api/schemas.py:1032-1034`), written straight
  to the row (`src/cyo_adventure/api/profiles.py:102-103`, `:286`). Sibling fields in the same
  file are far stricter: `PinCode` uses a regex (`schemas.py:1038`) and banned themes strip
  control characters and enforce a charset pattern (`schemas.py:1050-1051`) specifically because
  they flow into a generation prompt. Promoting `display_name` into rendered story content
  requires it to pass the structural checks and the band-mandatory denylist floor in
  `validator/slots.py`, both when the guardian sets it **and** again at render time, since a name
  set before this feature shipped was never checked.
- ⚠️ **English-only morphology.** Possessives usually survive a token swap; articles usually do
  not ("an Explorer" reads correctly, "a Maya" does not). The name slot is therefore most reliable
  in dialogue and ending titles. Note that the "never name the protagonist in body text" rule is
  narrower than it sounds: `drafting_guide.md:105` scopes it to body text only, and the fill-stage
  templates (`fill.md`, `fill_bound.md`) restate no such rule at all, so a per-slot audit of where
  a name can actually land is required rather than assumed.
- ⚠️ **Pronoun substitution is a per-skeleton audit, not a feature flag.** Gendered pronouns are
  hardcoded in beats and choice labels across the catalog. Whatever fraction of the catalog is
  pronoun-parameterized after the audit is the fraction this ever works on.
- ⚠️ **A new consent artifact to maintain.** One ring-2 disclosure record per (child
  profile, connection), enumerating the slot types it covers, is still more bookkeeping than the
  single account-level consent already built for ADR-018 D1, and it inherits that decision's open
  counsel question about what constitutes a valid signature. (An earlier draft of this bullet
  described a per-slot, per-ring, per-connection consent model; that is superseded by the
  single-record rule in section 3 and is not what gets built.)
- ⚠️ **"Dual consent" on a connection is two records, not two independent decision-makers.**
  ADR-016's `family_connection` requires a consent from each side, and this ADR layers a
  sharer-side disclosure consent on top. It is worth naming plainly that in the common case these
  are **one guardian's decision, recorded more than once**: the same adult signs for the sharer
  family and, in the sibling case, signs on behalf of two different children. Calling it "dual
  consent" flatters the mechanism. The accurate description is **dual-record, single-guardian**,
  and what it actually buys is auditability and revocability, not independent judgement by two
  parties. Wherever this ADR or its implementation plan calls a disclosure "dual-consented", read
  it that way.

### Technical Debt

- Nothing in this ADR exists in code today. The new slot kind, the sentinel-preservation
  mechanism, the post-fill sentinel-integrity check, the toggles, the consent events, the values
  payload, the client resolver, and the kid-visible indicator are all unbuilt.
- No post-fill check currently verifies that a published blob contains exactly the declared
  sentinel token set per node, with no mutated or forged tokens. The existing charset rule
  (`validator/slots.py:380-431`) blocks forgery on the **value** side (it rejects `{`, `}`, `<<`,
  `>>` in a bound value) but nothing checks the **prose** side, where the LLM writes freely.
- Ring 3 has no implementation to exclude from yet: ADR-016 records ring-3 aggregation as unbuilt
  (ADR-016, "Technical Debt"). The exclusion is therefore a forward-binding design constraint on
  whoever builds it, and needs to land as a test in the ring-3 work, not only as a sentence here.

## Validation

### Success Criteria

- [ ] A stored `storybook_version.blob` for a personalization-eligible story contains only
      sentinels and generic defaults; an automated test asserts no real profile value can appear
      in any blob, under any toggle state.
- [ ] `assert_prompt_pii_safe` is unchanged, and a test asserts a personalization-eligible
      generation job still raises on a seeded real child name.
- [ ] Two sibling profiles on one device, with different toggle states, read from the same cached
      `id@version` blob and see different rendered text. The application resolves each profile's
      values only from that profile's own payload record, and switching profiles switches the
      payload. Note the honest limit: both records sit in the same origin's IndexedDB, so this is
      an application-level access boundary, not a device-level isolation guarantee; a device
      shared by siblings is a shared trust boundary, exactly as it already is for the shared
      `storybooks` cache.
- [ ] Turning a toggle off removes the local values payload on the next app open, and a test
      asserts the rendered text reverts to generic.
- [ ] A cover-art prompt built from a personalization-eligible blob contains no sentinel token and
      no real value (`covers/prompt.py`); likewise a recommendation payload
      (`api/recommendations.py`), a rescreen re-read, and every pipeline event payload.
- [ ] A story reachable through any ring-3 surface renders fully generic regardless of every
      toggle, asserted as a test in the ring-3 work when it lands.
- [ ] A cross-family values fetch returns nothing unless **all** of: the connection is active
      (both guardians consented), the subject profile's `real_name_ring2_enabled` is true, and a
      ring-2 disclosure consent row exists for that (profile, connection) pair. Revoking any one of
      the three causes the **next** fetch to return nothing; a device already holding a payload
      reverts on its next successful fetch or app open, not instantly mid-session while offline.
      Revocation here is prospective, exactly as it is at ring 1.
- [ ] A profile `display_name` that fails `validator/slots.py` structural checks or the
      band-mandatory denylist floor cannot be substituted, and the reader falls back to the
      generic default rather than rendering it. The same check applies to every stored slot value,
      not only the name.
- [ ] A published blob whose sentinel multiset does not exactly match the declared set is rejected
      before it can be approved.
- [ ] The kid-visible control is present on every personalized book. A child may turn substitution
      off and back on **within the envelope their guardian has already consented to**, and can
      never enable a slot or a ring the guardian has not enabled. Turning it off never requires an
      adult; turning it back on never widens the disclosure.
- [ ] For the 3-5 band, no child-facing control is rendered at all, and the guardian setting
      surface says so.
- [ ] Route A's block still fires unchanged: `tests/unit/test_interpretation.py`'s
      `IDENTITY_PROTECTION` cases pass without modification.

### Owner decisions (all closed 2026-07-25; counsel gate closed by owner review 2026-07-29)

Every decision below was confirmed by the account owner on 2026-07-25. Following ADR-018's
convention, "owner choice recorded" and "counsel confirmed" are tracked as separate events. The
counsel items under OD-1 and OD-5 were closed by owner review on 2026-07-29 (the project has no
external counsel; the owner's review is the operative sign-off at R1 scale), which is what moved
this ADR from Proposed to Accepted. OD-5's closure is conditional; see its block.

- [x] **OD-1: Ring 2 separate disclosure consent.** **Decision confirmed 2026-07-25 (owner choice;
      pending counsel confirmation).** Confirmed as designed: ring-2 real-name substitution
      requires its own separate, separately-worded disclosure consent event, distinct from
      ADR-016's connection consent and never riding on it. This is a **deliberate divergence** from
      PR #415's B6 precedent, which held that mutual connection consent alone suffices for
      recommendation attribution. The rationale is unchanged and stands as recorded in the
      coordination section below (repetition, audience, and compounding, not novelty of the datum);
      the owner confirmed the conclusion without asking for the reasoning to be revised.
      **Flagged for counsel**: whether the divergence from B6 is defensible as drawn, and whether a
      layered disclosure consent on top of a connection consent is the right instrument. This was
      one of the two items that kept this ADR at Proposed.
      **CLOSED 2026-07-29 (owner review; no external counsel exists at this deployment scale).**
      Separate consent confirmed, chosen explicitly for conservatism: the incremental work is
      minimal and it reduces risk. The layered instrument stands as designed; the divergence from
      B6 stands as drawn.
- [x] **OD-2: Pronoun set at ring 1.** **Decision confirmed 2026-07-25 (owner choice).** Confirmed
      as designed: pronouns are a legitimate v1 personalization field; the value is **stored** as
      an explicit guardian-set field, never inferred from any other profile attribute; v1 is scoped
      to she/her and he/him only; they/them is deferred for the verb-agreement reason already
      documented in the taxonomy (singular "they" changes conjugation, which a token swap cannot
      retrofit onto already-conjugated stored prose). Ring 1 only, unchanged.
- [x] **OD-3: Route A copy.** **Decision confirmed 2026-07-25 (owner choice), resolved differently
      from either option originally offered.** Rather than the two workstreams negotiating wording
      or racing independent edits, **ADR-023 completes this work first and drafts the replacement
      copy, and PR #415 is asked to adopt this ADR's structure and wording.** The drafted copy is
      now literal text in the coordination section's Ask 1 below, covering both the Route A
      `IDENTITY_PROTECTION` disposition pair (made toggle-aware) and PR #415's A11 request-page
      line (kept static and true in every toggle state). Sequencing, not negotiation.
- [x] **OD-4: The ring-2 catalog-visibility surface.** **Decision confirmed 2026-07-25 (owner
      choice).** Ring 2 is in v1 (already decided earlier), and the remaining question is now
      closed too: **the catalog surface is accepted for v1.** A catalog book whose personalization
      subject sits in a connected family is an acceptable v1 delivery surface, and
      connection-scoped book visibility is **not** a v1 prerequisite. This is safe because the gate
      is on the values fetch rather than on the book (section 3a), so the same catalog book renders
      fully generic for every unconnected family. Connection-scoped visibility remains available as
      a later product feature on its own merits.
- [x] **OD-5: The sibling and pet-name raise to ring 2.** **Decision confirmed 2026-07-25 (owner
      choice; pending counsel confirmation).** All three sub-questions confirmed as designed:
      **(a) Parental-responsibility assumption: accepted with attestation.** An explicit
      attestation in the ring-2 consent ceremony ("I am the parent or legal guardian of [sibling]")
      is sufficient; the sibling slot does **not** need to stay ring 1 pending independent
      verification of authority. Implementation plan 10.1.1 item 3 carries the wording and
      `sibling_authority_attested` records it.
      **(b) Consent-copy scope: adequate as drafted.** Ceremony wording that explicitly covers
      "this child's name appearing in any of this family's stories shared with the connected
      family" is sufficient to authorize a companion appearance in a sibling's book. No separate,
      narrower consent event is required for companion appearances specifically.
      **(c) Bundled consent: adequate.** One bundled per-(profile, connection) consent record
      covering every opted-in slot type, including the sibling and pet-name entries, is sufficient.
      Those two do not need their own separate signature. By extension the related question in
      the implementation plan (section 14, closed question 4) is closed the same way: narrowing `covered_slot_types`
      updates the signed record in place and does not require re-signing.
      **Flagged for counsel**: this is the most legally aggressive choice in the ADR, and the
      attestation in (a) is a self-declaration rather than a verification. It was the second of
      the two items keeping this ADR at Proposed.
      **CLOSED CONDITIONALLY 2026-07-29 (owner review; no external counsel exists at this
      deployment scale).** Self-verification (the attestation) is accepted **for R1 only**, where
      deployment is immediate-family: the attesting guardian and the named sibling live in the
      same household, so the attestation is verifiable by direct knowledge. Conditions attached
      by the owner:
      1. **Reassess at every deployment-phase boundary.** This closure does not carry forward
         automatically; each phase gate (R2/TestFlight, R3/App Store, any commercial
         availability) must re-open OD-5 and re-decide with the then-current audience in view.
      2. **Hard revisit before iOS or commercial use.** At that point self-attestation is
         unlikely to suffice on its own (see the regulatory classification below) and real
         counsel review is expected.

      **Regulatory classification (owner-requested clarification, 2026-07-29; planning-grade
      analysis, not legal advice):** the OD-5 risk is primarily a **COPPA
      verifiable-parental-consent risk, deferred, not a present one**. COPPA (15 U.S.C.
      6501-6506, 16 CFR 312) binds operators of **commercial** websites/online services directed
      to children; the R1 deployment (private, non-commercial, immediate family) does not meet
      the operator definition, so no COPPA obligation attaches today. At commercial launch
      (ADR-008 track), collecting a sibling child's name and disclosing it to a connected family
      is collection-plus-disclosure of a child's personal information, requiring verifiable
      parental consent from THAT child's parent; a checkbox self-attestation by the requesting
      guardian is unlikely to satisfy 312.5 on its own. **GDPR/GDPR-K (Art. 8) is contingent, not
      inherent**: it attaches only if the service is offered to EU data subjects, with
      member-state parental-consent ages of 13-16; no EU availability is planned at R1 or R2, so
      it becomes live only if commercial scope includes the EU. ADR-018's compliance framework
      carries the tracking obligation; the D5 closeout task folds this classification into
      ADR-018 P7-08.

Separately, and not an OD: the **3-5 band** question raised in section 9 is also closed.
**Decision confirmed 2026-07-25 (owner choice):** personalization is offered to the 3-5 band as
designed, guardian-controlled, with no child-facing control rendered at that band.

### Review Schedule

- Initial: when the new slot kind and the sentinel-preservation mechanism land, before any toggle
  UI is built.
- Compliance: fold into ADR-018's P7-08 checklist as a new processing purpose; this feature
  changes what the privacy notice and the data classification must say, even though it adds no
  new provider counterparty.
- **OD-5 standing reassessment (owner condition, 2026-07-29): re-open OD-5 at every
  deployment-phase boundary** (R2/TestFlight, R3/App Store, any commercial availability). The
  R1 acceptance of self-attestation is scoped to immediate-family deployment and does not carry
  forward; before iOS or commercial use, expect real counsel review against the COPPA
  verifiable-parental-consent analysis in the OD-5 closure block.

## Coordination with parallel workstreams (PR #415, PR #416)

Both PRs are open and unmerged as of 2026-07-25. Neither of their planning documents exists on
`main` or on the current working branch; the file paths below resolve only on the PR branches.
This section is written to be handed directly to those workstreams.

### PR #415 (`docs/planning/story-diversity-plan-v2.md`, docs-only, unmerged)

**Ask 1 (item A11): adopt the copy below.** Per OD-3, this is a sequencing decision, not a
negotiation: ADR-023 finishes first and drafts the replacement wording, and PR #415 is asked to
**adopt this structure and text** rather than draft its own in parallel. That avoids two
workstreams converging on two different promises about the same mechanism.

The problem being fixed: A11 plans a "Who's the hero?" field on the kid-facing request page,
pre-filled with a made-up name plus a shuffle control, and one affirmative PII line, "Everyone in
the story gets a made-up name, even your friends." That sentence is true today and becomes
misleading the moment a family opts in under this ADR, including on a connected family's devices
at ring 2. The claim that never softens is about **generation**: every character is written with a
placeholder, no real child's name ever reaches a provider or gets stored in the story. What changes
is what a reader **sees**. The copy below keeps the first claim and stops implying the second.

**A11 replacement, kid-facing (static page copy, true in every toggle state, no branching):**

> Everyone in the story starts with a made-up name, even your friends. Ask your grown-up if you
> want your own name to show up when you read.

**A11 replacement, guardian-facing (help text or tooltip on the same surface):**

> Every story is written with made-up names for every character. No real child's name is ever sent
> to an AI provider or stored inside the story. If you turn on name personalization for a profile,
> that child's own name is filled in on your own devices as they read (see ADR-023).

"Starts with" is doing the load-bearing work: it is unconditionally true (generation always uses a
placeholder), it needs no per-request branching, and it does not promise the reader something their
family may have deliberately changed.

**Ask 1b: the Route A disposition copy, which this ADR is changing itself.** Not an ask of #415,
recorded here so the two stay consistent. The `SET_ASIDE` / `IDENTITY_PROTECTION` pair in
`ws7-request-interpretation-design.md`'s disposition table (backing
`story_requests/interpretation.py:1017-1035`) currently asserts an absolute to the child and then,
for an opted-in family, is contradicted by the very next thing that child reads. It becomes
**toggle-aware**: the toggle-off text is unchanged from today, and a toggle-on variant is added.

| Band group | Toggle OFF (unchanged) | Toggle ON (new) |
|---|---|---|
| Young (3-5, 5-8) | Heroes in our stories always have made-up names, so we chose one for you! | Every hero starts with a made-up name. Your name might show up when you read! |
| Middle (8-11, 10-13) | Heroes in our stories always have made-up names, so we chose one for this adventure! | Every hero starts with a made-up name. Your grown-up turned your real name on, so watch for it when you read! |
| Teen (13-16, 16+) | Heroes in our stories always use made-up names, so we chose one for this adventure. | Every hero starts with a made-up name. Your grown-up turned on name personalization, so your own name may appear when you read. |

Guardian text, toggle ON (toggle-off keeps today's string, with the stale "Section 5 Decision 4"
citation corrected to Section 5 "Self-naming" in both):

> The request asked to use the child's real name or self as the protagonist; self-naming is
> disallowed by design (Route A, coppa-gdpr-remediation-plan.md Section 5 "Self-naming"), so a
> fictional protagonist was used and no real name reached the generator. Name personalization is
> enabled for this profile, so the child's own name may still be substituted at read time on your
> devices (ADR-023).

That guardian line has to make both halves explicit, because they are genuinely different
mechanisms and a guardian seeing "declined" followed by their child's name in the book would
otherwise reasonably conclude the decline did not work. Route A is unchanged; personalization is a
separate, later, client-side step.

**Ask 2 (item A11): answer the shuffle-semantics question.** A11 does not say whether the shuffle
changes what is stored or generated for that story, or is purely a cosmetic client-side choice
among generic names. The plan itself lists "Does a hero-name field with a shuffle land as a toy or
as a restriction?" as an open user-testing question. That answer determines whether A11 and this
ADR's sentinel and eligibility mechanism interact at all: a shuffle that only picks among generic
names is orthogonal and needs no coordination, while a shuffle that changes the stored bound value
touches the same slot the personalization sentinel occupies and must be sequenced against it.

**Tension to resolve, not to race (item B6).** B6 was closed by owner decision on 2026-07-25:
sharing a child's first name with a connected family through the existing recommendation
attribution surface (`display_name` shown next to a recommendation) is acceptable on the strength
of ADR-016's mutual connection consent alone, with no additional disclosure consent layered on
top. That decision also commits to adding a sentence to ADR-016 recording ring-2 attribution
granularity.

This ADR's section 3 sets a **stricter** bar for the same child's same first name in a
neighbouring context. Both positions can be right, and the argument for why they legitimately
differ is about bandwidth and richness of disclosure rather than about the datum:

- A recommendation attribution is a **single, low-bandwidth signal** attached to a pointer: this
  named child liked this book. It is one fact, rendered once, in a feed surface the receiving
  guardian opted into seeing.
- A name substituted throughout full story prose is the **same datum delivered continuously**,
  across every passage of a book that may be re-read many times, and it is read directly by the
  other household's *children* rather than surfaced to its guardian. Repetition and audience, not
  novelty of the datum, are what make it a larger disclosure.
- It also arrives **compounded**. Under the taxonomy as finally settled, a ring-2 disclosure can
  carry, in one book: the child's first name, a sibling's first name, a pet's name, a kinship
  label, favourites, a home type. Individually trivial; together, and repeated across a book, a
  recognisable portrait of a named child and their household. An attribution line carries exactly
  one of those and never compounds.

  One honest bound on that third point. Pronouns (row 2) remain ring 1 only, so the most
  identity-sensitive slot never participates in a ring-2 disclosure. And an earlier draft of this
  ADR made this argument while the taxonomy still capped sibling and pet name at ring 1, which made
  the compounding claim untrue at the time. It is true now because rows 3 and 4b were raised
  deliberately, with reasoning recorded in the taxonomy section above, and not because the argument
  needed propping up.

That is the honest argument for the asymmetry. It is not obviously decisive, and this ADR does not
claim to have settled it on the merits. The owner confirmed the conclusion on 2026-07-25 (OD-1)
without asking for this reasoning to change, so the divergence from B6 is now a recorded decision
rather than a proposal, and counsel review is the remaining gate. What this ADR does claim is that
the two asks must
be reconciled in **one** edit to ADR-016, not two racing ones. B6 wants a sentence added recording
ring-2 attribution granularity; this ADR wants ring-2 personalization granularity recorded
alongside it. Whoever writes that amendment should write both, or neither, in a single change.

### PR #416 (`docs/planning/story-quality-lessons-2026-07.md` family, real code, unmerged)

**No direct conflict with this feature's mechanism.** Confirmed: PR #416's code changes touch
`validator/{policy,layer2,series,reading_level,band_profile}.py`,
`moderation/{classifiers,rescreen}.py`, `mutation/identity.py`, `generation/skeleton_match.py`,
`api/{generation,node_edit}.py`, `app.py`, and `story_requests/screening.py`. It does not touch
`storybook/theme_contract.py` or `validator/slots.py`, which are the two files this feature
extends.

Two notes worth recording:

1. **The authoring-lessons directive will bind this work.** PR #416 adds a new project-wide
   CRITICAL directive to `CLAUDE.md` ("Authoring Lessons Requirement") mandating that any
   authoring or validator work append lessons to `docs/planning/authoring-lessons-log.md`, with a
   `scripts/check_lessons_log.py` validator. This feature's implementation is validator work by
   that definition, so once #416 merges, the personalization workstream must log its lessons
   there. The implementation plan records this as a standing obligation.
2. **PR #416's engagement-analytics rollup is consistent precedent for the ring-3 rule, not a
   dependency.** Its `docs/planning/reader-path-engagement-design.md` independently designs the
   same anonymization discipline this ADR's ring-3 exclusion requires: a de-identified permanent
   aggregate with "No child id, no device id, no timestamps finer than a day", a proposed
   minimum-population floor of 5 distinct trails, aggregate endpoints that are
   "aggregate-BY-CONSTRUCTION, not aggregate-by-query" with no route accepting a
   `child_profile_id`, and rollup-then-purge of the raw child-linked trails 30 days after close.
   Cite it as convergent precedent. This ADR takes no dependency on it and neither blocks the
   other.

### Aside: the SR-8 rule-ID collision (affects the same two PRs, not this feature)

Recording this because it sits between the same two open PRs and will be cheaper to fix before
either merges. PR #415 item B3 proposes a new validator rule ID `SR-8` for full ending-state
admissibility across series continuations, noting "the ID is free; `SR-7` is the current maximum".
That was true of the working branch and is no longer true of PR #416, which has already
implemented and tested a **different** `SR-8` (carried-variable declaration integrity: ERROR on a
narrowed range or changed type, WARNING on a dropped variable) in `validator/series.py`, catalogued
in `docs/planning/validator-rules.md`. If #415 proceeds under the same ID it will collide with
shipped code. Recommendation: #415 takes `SR-9`, or folds its broader ending-state check into the
gap PR #416 already tracks, which its `authoring-lessons-log.md` item AL-038 names as
unfinished ("Still open: the read-time carry audit and gating the continuation offer on a
satisfying ending").

## Verification notes: where the live repo differs from the working assumptions

Recorded so a reader does not inherit a stale premise from the design conversation this ADR came
out of.

Every catalog count in this section was measured on 2026-07-25 against a 61-skeleton catalog. The counts are
left as measured because each dates a verification rather than asserting live state; for current totals see
[catalog-census.md](../catalog-census.md) (`UW-G24`).

- **The Route A citation is imprecise, and the code repeats it.** The remediation plan has no
  numbered "Section 5 Decision 4". The self-naming ruling lives as the third bullet of Section 2
  ("Foundational decisions", `coppa-gdpr-remediation-plan.md:204-206`) and as the "Self-naming"
  entry in Section 5's "Resolved, kept for reference" (`:725-759`). The stale citation is
  reproduced verbatim in code at `src/cyo_adventure/story_requests/interpretation.py:174`, so it
  should be corrected in both places or in neither.
- **No theme contract uses a `pattern` constraint.** `SlotConstraints` declares `pattern`
  (`storybook/theme_contract.py:73`) and `validate_slot_bindings` enforces it
  (`validator/slots.py:645-653`), but no `.contract.json` in the catalog sets one; every one of
  the 2,610 declared slots uses exactly `max_words`, `forbid`, and `distinct_from`. Any design
  relying on `pattern` as an existing, exercised mechanism is relying on untested code.
- **`HERO` is common but not universal.** 61 skeletons exist, 45 have a theme contract, and 39 of
  those declare a `HERO` slot. Sixteen skeletons have no contract at all. Eligibility therefore
  cannot be assumed catalog-wide, which is why section 5 makes it a per-story marker.
- **No skeleton contains filled prose.** Every node body in the catalog is a `<<FILL ...>>`
  directive, so the hardcoded gendered pronouns are in beats guidance and choice labels, not in
  stored prose. This makes the pronoun problem an authoring-content problem rather than a
  regeneration problem, and it means a pronoun audit is an audit of directives.
- **The "never describe the reader-protagonist" rule is weaker than assumed.** The only rule found
  is "Address the reader as 'you,' never 'the protagonist' or a character name in body text"
  (`generation/templates/drafting_guide.md:105`). It covers naming, not describing, and it is
  scoped to body text, leaving choice labels, ending titles, and beats uncovered. `fill.md` and
  `fill_bound.md` restate no POV or naming rule at all. Exclusion #12 (appearance) still holds on
  its cover-art argument, but it should not lean on a prose rule that is narrower than stated.
- **The interpretation renderer does NOT have profile access, contrary to a working assumption in
  this decision round.** Making the Route A copy toggle-aware was described as a small change
  because "the disposition renderer already has access to the requesting child's profile". It does
  not. `render_interpretation` (`story_requests/interpretation.py:1249-1257`) takes `elements`,
  `band`, `layer`, `created_at`, `skeleton_slug`, and `contract_version`, and its docstring pins it
  as a pure function ("Pure: builds `kid_text` / `guardian_text` for every element from the
  template catalog ... `created_at` is supplied by the caller so the module reads no wall clock").
  The template catalog is keyed `(disposition, reason, band_group)` (`:706`) with no profile axis.
  The change is still small, but it is a **signature change plus a catalog-key change**, not a free
  branch: see implementation plan section 12 for the shape (a `bool` parameter, deliberately not a
  profile object, so the module's purity discipline survives) and for the five production call
  sites it touches.
- **Save-state exports are safe, as assumed.** `ReadingState` carries node ids and variable state
  only (`frontend/src/player/types.ts:71`), so no substituted text can ride a sync or replay
  payload.
- **One additional surface not in the original list: text-to-speech.** `tts_enabled` is a
  per-profile setting (`db/models.py:445`) and `useReadAloud.ts` uses the browser
  `window.speechSynthesis` API, which on several platforms is cloud-backed. A personalized passage
  read aloud therefore may leave the device through a path the app does not control. This is not a
  blocker, but it belongs in the leak-surface register rather than being discovered later.
- **The ADR index was missing ADR-020.** `docs/planning/adr/README.md`'s index table skipped from
  ADR-019 to ADR-021 even though `adr-020-mutation-derived-skeletons-and-catalog-growth.md`
  exists. **Fixed in this same change**, since the table was already being edited to add ADR-023;
  the row records Accepted / 2026-07-20, matching that file's own status line.

## Amendment (2026-08-06): the `character_name` personalization slot [SUPERSEDED 2026-08-07]

> **Superseded on 2026-08-07 by section 11, "Amendment (2026-08-07): the `character_name` slot",
> above.**
> Kept for the record; do not implement from it. It sits later in this file than the amendment that
> replaces it purely because it was appended after the body, which is exactly why this banner is
> here. Three of its claims were falsified once the slot was actually built, and section 11 is the
> authority on all three:
>
> - **Shape.** This section calls the slot "free text" alongside `pet_name`. It is not: the
>   `character_name` row carries **no** value column at all, and
>   `ck_cpp_value_cardinality` rejects any value field set on this slot type. The value is
>   synthesized at render time from the active `character.name`.
> - **DB CHECK impact.** This section says "no DB CHECK migration on `slot_type`, no change to
>   three-shape validation". Both happened: `ck_cpp_slot_type` moved to a closed 12-value
>   vocabulary, and the old flat `ck_cpp_exactly_one_value` had to be renamed and made
>   slot-scoped as `ck_cpp_value_cardinality`, because this is the first slot for which zero
>   values is the correct shape.
> - **Clearing semantics.** This section says the guardian "can clear it". Turning the toggle off
>   is the *only* way to clear it; blanking the character's name is not a clear, since the child
>   can rename the character and the slot repopulates.

[ADR-028](./adr-028-persistent-reader-characters.md) adds a persistent reader character. Its name must be
able to render in prose, which needs a personalization slot. Personalization is keyed
`(child_profile_id, slot_type)` with one value per child forever, which does not fit a per-character mutable
name.

**Resolution: add the slot type, but source its value from the active character row.** `character.name` is a
column; the per-profile values payload gains a `character_name` field resolved from whichever character is
active. No primary-key change, no DB CHECK migration on `slot_type`, no change to three-shape validation.
The resolver learns one new source.

| Property | Value | Why |
|---|---|---|
| Slot | `character_name` | New entry in `PERSONALIZATION_FIELDS` (`src/cyo_adventure/storybook/theme_contract.py`) |
| Shape | Free text | Same category as `pet_name`, the existing free-text precedent |
| Ring ceiling | Ring 1 only, permanently | Profile-scoped; never renders on another household's device |
| `REAL_PERSON_PERSONALIZATION_FIELDS` | **Included** | A kid can type their own name. Treating it as fictional would skip the `role_safety` audit; including it forces `role_safety: "protagonist"`, which is also true. |
| Governance | Guardian-set toggle, **default off** | This ADR's governance model is guardian-controlled and opt-in. A kid-authored value inverts that, so the guardian holds an explicit per-profile enable, sees the current value, and can clear it. |
| Validation | `validator/slots.py` structural plus band-mandatory denylist, at set time **and** at render time | This ADR's explicit requirement for promoting a stored value into rendered content |
| Purge | `character.name` joins this ADR's purge paths | Must be confirmed against the concrete implementation rather than asserted; this ADR describes the requirement, not the wiring |

With the toggle off a character still works: rendering falls back to the existing
`protagonist_first_name` resolution. The character's mechanical and visual identity is unaffected.

`look` is deliberately **not** a slot. It is an avatar in library and reader chrome, never substituted into
prose, so it is an enum column with no compliance surface. Prose rendering of appearance would be a separate
amendment.

**Not implemented by this amendment.** The slot ships with the character API, not with the validator work in
ADR-028 steps 2 and 3. This section records the ruling so the implementation has an authority to cite.

## Follow-on work

Required by `adr/README.md` for any ADR materially amended after 2026-07-28. Section 11's
`character_name` amendment (2026-08-07) is such an amendment, and this section is where its
consequents get a home. Every item cites a register row or a phase; nothing here is left as
"future work".

- **Set-time validation on the slot's source column is ordered wrong**:
  [UW-C69](../unscheduled-work-register.md) (Phase 5). `CharacterName` (`api/schemas.py`) applies
  its `max_length=32` bound **before** `AfterValidator(_nfc)` normalizes, while
  `db/models.py`'s `name` column is `VARCHAR(32)`. Because NFC can change a codepoint count, an
  input that clears the bound can still overflow the column, surfacing as a database error rather
  than the 422 that section 11's "Validation" bullet promises. This is the one open defect the
  amendment itself creates.
- **The amendment's other three clauses are implemented, not follow-ons.** Recorded here so a
  future reader does not re-open them: the ring-1 ceiling and the `REAL_PERSON_*` membership are
  enforced in `storybook/theme_contract.py` and the `ck_cpp_ring2_ceiling` CHECK; the zero-value
  shape is enforced by `PersonalizationSlotBody` and `ck_cpp_value_cardinality`; and the purge
  coupling (consequence 2) is `PURGE_TARGETS[character_name] = "character"` plus
  `purge_profile_personalization()` in `api/personalization.py`, covered by
  `tests/integration/test_personalization_purge.py` and
  `tests/unit/test_personalization_purge_targets.py`.
- **Prose rendering of a character's appearance is out of scope, not deferred work.** The
  2026-08-06 block already ruled `look` is an avatar enum with no prose substitution and therefore
  no compliance surface. Adding one would be a new amendment with its own decision, so it gets no
  register row here; recording the boundary is what stops it drifting into an untracked assumption.
- **Standing, not new**: the OD-5 reassessment in "Review Schedule" above re-opens at every
  deployment-phase boundary, and [UW-H03](../unscheduled-work-register.md) carries the `G2` counsel
  gate. Neither is created by the 2026-08-07 amendment; both still govern it.

## Related

- [Implementation plan](../story-personalization-implementation-plan.md): phasing, guard points,
  data-model additions, and the risk register for this ADR.
- [ADR-016](./adr-016-recommendation-sharing-social-boundary.md): the three rings; the ring-3
  exclusion this ADR inherits; the pending ring-2 granularity amendment.
- [ADR-018](./adr-018-childrens-privacy-compliance.md): the consent-event pattern (D1) and the
  open compliance decisions this feature adds a processing purpose to.
- [ADR-019](./adr-019-parameterized-skeletons-theme-contracts.md): the slot and theme-contract
  machinery the new slot kind extends.
- [ADR-005](./adr-005-mandatory-human-approval.md): the approval gate this design keeps
  meaningful by never diverging the served artifact from the approved one.
- [coppa-gdpr-remediation-plan.md](../../compliance/coppa-gdpr-remediation-plan.md): Section 2
  bullet 3 and Section 5 "Self-naming" (Route A), plus the proposed Route A messaging caveat.
- [Privacy model](../privacy-model.md): needs a new entry for the client-held values payload as a
  child-linked data category that never reaches the server in content form.
- [ws7-request-interpretation-design.md](../ws7-request-interpretation-design.md): the disposition
  and reason-code model this ADR deliberately leaves unmodified.
- [Capability register](../capability-register.md): **G18** (guardian opts a child's real details
  in, per slot, ring-scoped) and **K20** (a child reads a story using their own details and holds
  a switch over it) were minted for this feature in register v1.8, with scope notes added to G4,
  G17, K19, S10, S11, and S12.

  The register's rule 3 requires a conscious call here, so the reasoning, not just the outcome.
  Cross-references alone were the tempting answer and they are not sufficient: G4 already promises
  "personalized stories" and its own example names a real child, but G4's mechanism is
  generation-time with real names kept out of prompts, so folding this in would make one row mean
  two incompatible things. S10 and S11 are genuinely *extended* by this feature (a new child-linked
  data category, a new kind of ring-2 flow) but they are cross-cutting guarantees, and a feature
  cannot be acceptance-tested against "privacy architecture". K16 is identity in the app, not
  identity in the story. Without new IDs the most user-visible thing this feature does would trace
  to nothing, which is the exact failure rule 3 exists to catch.

  Equally deliberately, **two IDs and no more**. No A-series entry: an admin reading marker-bearing
  prose at review is a presentation detail of A6's existing approval gate, not a new authority. No
  S-series entry: the sentinel and render architecture *implements* S10's invariant rather than
  adding a cross-cutting guarantee, so those rows get extended notes. Both new rows sit at ❌ until
  this ADR is Accepted and the work lands.
