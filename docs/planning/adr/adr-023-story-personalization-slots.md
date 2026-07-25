---
title: "ADR-023: Guardian opt-in story personalization (render-time slot substitution)"
schema_type: planning
status: proposed
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

> **Status**: Proposed (2026-07-25). Several choices below, above all the ring-2
> separate-disclosure-consent decision and its tension with PR #415's B6 resolution, need
> explicit owner and counsel sign-off before this flips to Accepted. This mirrors ADR-018's
> own convention: a proposed compliance-bearing ADR is itself the tracking signal.
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
default ceiling; ring 2 (a connected family) is allowed for a strict subset of slots and requires
its own separate disclosure consent; ring 3 is categorically excluded and always renders generic.

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
  (`adr-016-...md:99-102`) and treats anonymization as "a hard requirement, not an optimization"
  (`:146`). Anything visible outside rings 1 and 2 renders fully generic, without a toggle to
  change that.
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
generic default (for example `HERO` bound to `"Explorer"`), and whose rendered output carries a
machine-recognizable sentinel that survives verbatim through fill, validation, moderation,
approval, and storage. The generic default is what the LLM sees and what the sentinel renders to
for every non-opted-in reader; the sentinel is what the client looks for. Nothing about the value
side of the pipeline changes: the fill prompt still sees only generic text, and
`validate_slot_bindings` still runs unchanged over the generic binding.

### 3. Governance: per-profile toggles, default off, ring-scoped

- Two ring-scoped booleans per child profile, both defaulting to **off**:
  `real_name_ring1_enabled` and `real_name_ring2_enabled`. Ring 1 is a child's own family;
  ring 2 is a family connected by an active, dual-consented, directional, revocable
  `family_connection` (ADR-016 `:82-89`).
- **Ring 2 requires its own separately-worded disclosure consent event**, timestamped and
  policy-versioned, mirroring the paired `consent_accepted_at` / `consent_policy_version` /
  `consent_signer_name` / `consent_ip` columns already CHECK-enforced on `User`
  (`src/cyo_adventure/db/models.py:305-308`, `:385-395`) for ADR-018 D1. It must **not** reuse
  the account-level onboarding consent. The reasoning is that COPPA's 2025 amendments require
  disclosure consent to be obtained separately from collection consent; reusing one signature
  for both makes the disclosure unverifiable after the fact. This is a design position, not a
  legal conclusion, and is one of the two items flagged for counsel below.
- **Ring 3 has no toggle.** It is categorically excluded. Any surface visible beyond rings 1 and
  2, including any future ADR-016 ring-3 aggregate recommendation, always renders the generic
  sentinel default. There is no configuration that changes this.
- Consent bookkeeping is **per slot type, per profile, per ring**, and per connection at ring 2.
  It is recorded as pipeline events that carry the fact of consent and never the values, matching
  the PII-free payload allowlist contract already enforced in
  `src/cyo_adventure/events/writer.py:17-19`.

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

**Route A's messaging, however, needs a scoped addendum.** The kid-facing copy at
`interpretation.py:1019-1034` currently asserts an absolute ("Heroes in our stories always have
made-up names"). Once render-time substitution ships, that sentence is false for an opted-in
family, and at ring 2 it is false on another household's devices as well. The claim that stays
true, and that the copy should be reworded toward, is about egress and storage, not about what
appears on a screen. The implementation plan carries the copy change; the compliance plan carries
a proposed caveat note against the Route A record.

### 5. Eligibility is a per-story marker, not a global assumption

- For theme-contract-bound (parameterized) skeletons, name eligibility is whether the bound
  contract declares a `HERO`-equivalent identity slot. This is not universal: 45 of 61 skeletons
  in the catalog have a contract at all, and `HERO` is declared in 39 of those 45.
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
| 3 | Sibling or family-child name (a `COMPANION`-style slot) | High. A story with a real sibling in it is a distinct experience | Direct identifier for a *second* child who is not the consenting subject of this flow | High. Two real names plus any setting detail compounds fast | **Ring 1 only in v1** | **Include, profile-bound to another `child_profile` in the same family; ring 2 deferred** |
| 4a | Pet species | Moderate. Cheap warmth, near-zero identifier value | Not an identifier | Low | Ring 1 + ring 2 | **Include, closed enum only** |
| 4b | Pet name | Moderate | Weak identifier with outsized credential value | Real. A pet name is a classic security-question and social-engineering datum | **Ring 1 only** | **Include, free text at ring 1 only** |
| 5 | Trusted-adult kinship label ("Grandma", "Abuela", "Auntie", "Grandpa") | High. Kinship vocabulary is culturally specific and cheap to get right | Not an identifier; a relationship label, not a person | Low | Ring 1 + ring 2 | **Include, closed enum only. A real adult's personal name is excluded: a third party who never consented** |
| 6 | Favorite color, food, hobby | Moderate. Small, frequent hits of recognition | Preference data, not identifying | Low, given a closed vocabulary | Ring 1 + ring 2 | **Include, closed vocabulary lists only, never free text** |
| 7 | Home type (house, apartment, farm, ...) | Low. Occasionally grounds an opening scene | Coarse, non-identifying | Low. Explicitly not a location: see #9 | Ring 1 + ring 2 | **Include, closed enum, low priority** |
| 8 | Dedication or inscription line | High emotional value, zero prose risk | Contains a name and a kinship label already covered by #1 and #5 | Low, because it is template-constrained | **Ring 1 only** | **Include, template-constrained ("For {NAME}, love {KINSHIP}"), rendered as a title-page overlay outside the story blob, never injected as free text into a kid-facing prose surface** |

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
- ⚠️ **Ring 2 exports a real child's name into another household's devices.** That is a genuinely
  new child-linked data flow, of a different order from ADR-016's existing recommendation
  attribution. See the coordination section: this is the item most in need of sign-off.
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
- ⚠️ **A new consent artifact to maintain.** Per-slot, per-profile, per-ring, per-connection
  consent records are more bookkeeping than the account-level consent already built for ADR-018
  D1, and they inherit that decision's open counsel question about what constitutes a valid
  signature.

### Technical Debt

- Nothing in this ADR exists in code today. The new slot kind, the sentinel-preservation
  mechanism, the post-fill sentinel-integrity check, the toggles, the consent events, the values
  payload, the client resolver, and the kid-visible indicator are all unbuilt.
- No post-fill check currently verifies that a published blob contains exactly the declared
  sentinel multiset with no mutated or forged tokens. The existing charset rule
  (`validator/slots.py:380-431`) blocks forgery on the **value** side (it rejects `{`, `}`, `<<`,
  `>>` in a bound value) but nothing checks the **prose** side, where the LLM writes freely.
- Ring 3 has no implementation to exclude from yet: ADR-016 records ring-3 aggregation as unbuilt
  (`adr-016-...md:152-155`). The exclusion is therefore a forward-binding design constraint on
  whoever builds it, and needs to land as a test in the ring-3 work, not only as a sentence here.

## Validation

### Success Criteria

- [ ] A stored `storybook_version.blob` for a personalization-eligible story contains only
      sentinels and generic defaults; an automated test asserts no real profile value can appear
      in any blob, under any toggle state.
- [ ] `assert_prompt_pii_safe` is unchanged, and a test asserts a personalization-eligible
      generation job still raises on a seeded real child name.
- [ ] Two sibling profiles on one device, with different toggle states, read from the same cached
      `id@version` blob and see different rendered text; neither can see the other's values.
- [ ] Turning a toggle off removes the local values payload on the next app open, and a test
      asserts the rendered text reverts to generic.
- [ ] A cover-art prompt built from a personalization-eligible blob contains no sentinel token and
      no real value (`covers/prompt.py`); likewise a recommendation payload
      (`api/recommendations.py`), a rescreen re-read, and every pipeline event payload.
- [ ] A story reachable through any ring-3 surface renders fully generic regardless of every
      toggle, asserted as a test in the ring-3 work when it lands.
- [ ] A ring-2 render is blocked unless a separate, timestamped, policy-versioned disclosure
      consent exists for that profile, that slot type, and that specific connection; revoking the
      `family_connection` blocks it immediately.
- [ ] A profile `display_name` that fails `validator/slots.py` structural checks or the
      band-mandatory denylist floor cannot be substituted, and the reader falls back to the
      generic default rather than rendering it.
- [ ] A published blob whose sentinel multiset does not exactly match the declared set is rejected
      before it can be approved.
- [ ] The kid-visible indicator is present on every personalized book, and its veto is one-way
      (a child can turn substitution off, never on).
- [ ] Route A's block still fires unchanged: `tests/unit/test_interpretation.py`'s
      `IDENTITY_PROTECTION` cases pass without modification.

### Open decisions (close before Accepted)

- [ ] **OD-1: Ring 2 separate disclosure consent.** Confirm with owner and counsel that ring-2
      real-name substitution requires its own consent event rather than riding ADR-016's mutual
      connection consent. This is the direct tension with PR #415's B6 resolution; see below.
- [ ] **OD-2: Pronoun set at ring 1.** Confirm that pronouns are a legitimate personalization
      field at all, that deriving them requires a new profile field rather than an inference, and
      that they/them can be deferred without shipping something worse than nothing.
- [ ] **OD-3: Route A copy addendum wording.** Agree the replacement kid-facing and
      guardian-facing strings before any toggle ships, so the absolute claim is never live
      alongside a contradicting feature.
- [ ] **OD-4: Whether ring 2 is in v1 at all.** A defensible narrower v1 is ring 1 only for every
      slot, deferring the entire ring-2 consent mechanism.

### Review Schedule

- Initial: when the new slot kind and the sentinel-preservation mechanism land, before any toggle
  UI is built.
- Compliance: fold into ADR-018's P7-08 checklist as a new processing purpose; this feature
  changes what the privacy notice and the data classification must say, even though it adds no
  new provider counterparty.

## Coordination with parallel workstreams (PR #415, PR #416)

Both PRs are open and unmerged as of 2026-07-25. Neither of their planning documents exists on
`main` or on the current working branch; the file paths below resolve only on the PR branches.
This section is written to be handed directly to those workstreams.

### PR #415 (`docs/planning/story-diversity-plan-v2.md`, docs-only, unmerged)

**Ask 1 (item A11): do not ship the absolute copy.** A11 plans a "Who's the hero?" field on the
kid-facing request page, pre-filled with a made-up name plus a shuffle control, and one
affirmative PII line: "Everyone in the story gets a made-up name, even your friends." That
sentence is true today and becomes false the moment any family opts in under this ADR, including
on another family's devices at ring 2. Either scope the copy to a "by default" framing, or
coordinate the exact wording with this ADR so a single sentence stays true under both. The
underlying true claim, which does not soften, is about egress and storage: names in the story are
made up when the story is written, and nobody outside your family ever sees your real name in it.

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
  named child liked this book. It is one fact, in one place, in a surface the receiving guardian
  opted into seeing.
- A name substituted throughout full story prose, read repeatedly in another household, is a
  **much larger and richer disclosure**. It carries the name plus, by combination, whatever else
  the substituted slots reveal (a pet's name, a sibling's name, a kinship term), and it is read by
  the other family's *children*, not only its guardians.

That is the honest argument for the asymmetry. It is not obviously decisive, and this ADR does not
claim to settle it: OD-1 above is the sign-off gate. What it does claim is that the two asks must
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
- **Save-state exports are safe, as assumed.** `ReadingState` carries node ids and variable state
  only (`frontend/src/player/types.ts:71`), so no substituted text can ride a sync or replay
  payload.
- **One additional surface not in the original list: text-to-speech.** `tts_enabled` is a
  per-profile setting (`db/models.py:445`) and `useReadAloud.ts` uses the browser
  `window.speechSynthesis` API, which on several platforms is cloud-backed. A personalized passage
  read aloud therefore may leave the device through a path the app does not control. This is not a
  blocker, but it belongs in the leak-surface register rather than being discovered later.
- **The ADR index is missing ADR-020.** `docs/planning/adr/README.md`'s index table skips from
  ADR-019 to ADR-021 even though `adr-020-mutation-derived-skeletons-and-catalog-growth.md`
  exists. Flagged, not fixed here.

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
- [Capability register](../capability-register.md): this feature needs new G-series and K-series
  IDs before implementation starts, per the register's own "new proposals must cite the IDs they
  serve" rule.
