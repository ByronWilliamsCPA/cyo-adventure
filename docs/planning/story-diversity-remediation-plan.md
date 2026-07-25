---
schema_type: planning
title: "Story Diversity Remediation and Enhancement Plan"
description: "Phased plan to close the nine gaps in story-diversity-analysis.md and raise book diversity
  further. Records thirteen review corrections and owner decisions: the open-vocabulary theme signature is unsafe as drafted because
  the closed vocabulary is load-bearing for the WS-7 echo surface; the gamebook cells' 98% negative share is
  ADR-011-intended with PL-20 working as designed, the real gap being a shallow fail-path tail PL-20 leaves
  out of scope; expanding the curated vocabulary is the better fix and it exposes a symmetric-Jaccard defect
  that makes an identical premise score as dissimilar; the guardian family-only versus catalog two-prong is
  sound but blocked on visibility being set at approval rather than at intake; and visibility authorization is
  a monotone restriction rule where the guardian sets a ceiling the admin may lower but never raise, which a
  guardian may change later without any content re-screen because every content screen is already
  visibility-independent; PL-22's fraction resolves to 33% on measured funnel depth; and the request page must
  state its restrictions up front, because the three most surprising ones can never be explained afterwards; and
  'how many winning arcs' is the wrong question, since path mass and ending count are decoupled, which also
  exposes two series-continuity gaps. Identifies the root cause of the gamebook symptoms: ADR-011's
  restart-on-fail primitive is specified, unrepresentable in the schema, and half-built in the player, so every
  terminal is a hard stop. The resulting two-tier restart model (setbacks auto-loop, foreclosing terminals offer
  a choice) then narrows PL-22 from 178 endings to 73 and retracts the SR-8 series rule entirely, and an opt-in
  challenge mode adds a series reset on death for the two teen bands."
tags:
  - planning
  - generation
  - diversity
  - privacy
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Turn the current-state audit into an executable, sequenced plan with deliverable IDs, acceptance
  metrics, and the privacy and band-policy decisions each phase depends on."
component: Strategy
source: "story-diversity-analysis.md; review challenges on GDPR exposure of an open-vocabulary theme
  signature, on the 98% negative ending share in the gamebook cells, on expanding the curated tag list, and
  on a guardian-chosen family-only versus general-library split; follow-up read of
  publishing/state_machine.py::Visibility, api/assignments.py, api/library.py, diversity/history.py,
  adr-016-recommendation-sharing-social-boundary.md, and
  generation/worker.py::_degraded_set_aside_decisions, validator/band_profile.py, ADR-011 sections 6 and 8,
  privacy-model.md, player/engine.py, api/reading.py, validator/policy.py::_check_min_to_complete (PL-20);
  BFS win-path and fail-path depth measurement over the 14 production-eligible gamebook skeletons
  (2026-07-25)."
---

> **Companion documents.** [story-flexibility-plan.md](story-flexibility-plan.md) is the strategy of record.
> [story-diversity-analysis.md](story-diversity-analysis.md) is the current-state audit this plan executes.
> Finding references below (3.1, 3.2, ...) point at that audit's section numbers.

---

## 1. Corrections and refinements from review

Thirteen items, each from a review challenge and each changing the work. They are recorded here rather than
silently patched into the audit, because each rests on a fact the audit did not establish. 1.1 and 1.2 correct
errors; 1.3 through 1.10 are owner direction and resolved decisions that reshape the approach. 1.6 also
corrects an earlier claim about offline revocation, and 1.9 replaces a deliverable that measured the wrong
thing, 1.11 identifies the root cause the P4 measurements were symptoms of, 1.12 simplifies three
deliverables and retracts one, and 1.13 adds an opt-in challenge mode.

### 1.1 The open-vocabulary theme signature is unsafe as drafted

The audit's top recommendation was to replace `theme_signature`'s closed 12-tag vocabulary with an
open-vocabulary content-token signature. **As drafted that is a privacy regression, not just a diversity
fix.** The closed vocabulary is load-bearing for a surface the audit did not trace.

`generation/worker.py::_degraded_set_aside_decisions` turns each returned tag into a
`RawElement(phrase=tag)`, feeds it to `derive_dispositions`, and renders it through
`render_interpretation` into the WS-7 request interpretation: a kid-facing echo plus a guardian caption,
persisted on the story request. The code says so explicitly, twice:

```text
decompose the premise into WS-0 theme_signature tags (each catalog vocabulary and
echo-safe by construction, so no premise substring leaks)
```

The closed vocabulary is what guarantees that no substring of a child's free-text premise is ever rendered
back or stored in a derived artifact. Open the vocabulary in place and the tags become arbitrary premise
tokens, which for real requests means pet names, sibling names, a school, a street, a grandparent, a medical
detail. Those would then be:

- rendered to a kid-facing echo and a guardian caption,
- persisted in `RequestInterpretation` as a new artifact containing children's personal data,
- and, since interpretation text re-enters downstream prompts, exported to an LLM provider.

Under GDPR that is a data-minimisation problem (Art. 5(1)(c)), a purpose-limitation problem (Art. 5(1)(b),
new derived artifact for a new purpose), a storage-limitation problem unless it inherits the premise's
retention (Art. 5(1)(e)), and it lands squarely in the children's-data regime that
[ADR-018](adr/adr-018-childrens-privacy-compliance.md) and [privacy-model.md](privacy-model.md) govern. It also
widens the OWASP LLM01 surface that safety invariant 4 already flags.

**Corrected design: split one function into two signatures with different postures.**

| | Echo signature | Similarity signature |
| --- | --- | --- |
| Purpose | WS-7 kid echo and guardian caption | WS-4 selection weighting, ATG partner choice |
| Vocabulary | **Closed and curated** (today's `_THEME_TAG_MAP`) | Open, entity-masked content tokens |
| Rendered to a user | Yes | **Never** |
| Persisted | Yes (in `RequestInterpretation`) | **Never** (derived at read time, in-memory only) |
| Enters an LLM prompt | Yes, as today | **Never** |
| Personal data at rest | Unchanged from today | **None added** |

The similarity signature is privacy-safe precisely because of those four "never"s. It is computed at query
time from the premise the family already lawfully supplied for story generation, used to pick a number, and
discarded. It creates no new personal data at rest, so there is no new retention or erasure obligation, and
nothing new to export. Entity masking is belt-and-braces on top: `diversity/normalize.py` already ships
`extract_entities` and `mask_tokens` with a single `ENTITY_PLACEHOLDER`, built for exactly this, so names
collapse to `<ent>` and contribute zero distance before the signature is even formed.

The diversity benefit survives the split intact, because diversity only ever needed the internal number. The
audit conflated the two consumers; separating them gets the coverage without touching the echo guarantee.

Two consequences for the plan: the echo path must be held byte-identical (D1 is a pure split, no behaviour
change), and `privacy-model.md` must gain a short entry recording the similarity signature as a
transient, non-persisted, non-exported derivation, with a DPO or legal read on whether the DPIA needs an
addendum. That is a judgement call this plan flags rather than makes.

### 1.2 The 98% negative ending share is intended, PL-20 works, and the real gap is the fail path

> **Revised 2026-07-25 after a second review challenge.** An earlier version of this section described
> `_MIN_COMPLETE` as "a reachability floor, satisfied by a single arc existing" and compared it against a
> random-walk mean depth of 4 to 9 nodes. Both were misleading. `_MIN_COMPLETE` is a floor on the *length of
> the shortest winning path*, it is the deliberate age-appropriate-depth guarantee, and it passes with margin
> on every production skeleton. The corrected finding below is narrower, better evidenced, and much cheaper to
> fix.

The challenge was that 98% of endings ending badly seems high. Checking it against policy: **the ratio itself
is ADR-011's stated design intent, and nothing in the validator constrains it.**

- ADR-011 section 6: "Gamebook endings are 'few wins + many fails' (~25-35% of nodes are terminals)". The
  gamebook cells conform on terminal fraction: 27.6%, 30.0%, 30.9% for the three long trees.
- `validator/band_profile.py` enforces `forbidden_ending_kinds` (no `death` below 10-13), `min_endings`,
  `min_decisions`, and `_MIN_COMPLETE`, enforced as **PL-20** in `validator/policy.py`. Grepping the validator
  for `valence` returns **nothing**: valence is a declared field used for diagram styling and diversity
  metrics only.

So 98% is not a rule violation. It is the Fighting Fantasy convention the style was designed around, and it
arrived by convention rather than by decision, since no rule sets it.

**PL-20 is the age-appropriate-depth guarantee, and it works.** Its own docstring states the design exactly:

```text
PL-20: the shortest satisfying-completion path must meet the arc floor.
The shortest path in nodes from start_node to any success/completion ending must be at
least that floor; a too-short winning path (a hollow quick win) blocks.
Fail-fast negative endings are unaffected.
```

Measured against every production-eligible gamebook skeleton, it passes with margin everywhere. Shortest
winning path versus the cell floor, plus the depth distribution of negative endings (BFS node depth from
`start_node`, conditions ignored):

| Skeleton | Floor | Shortest win | Shortest fail | p10 fail | Median fail | PL-20 |
| --- | --- | --- | --- | --- | --- | --- |
| the-harrowstone-keep | 32 | 59 | **3** | 18 | 39 | ok |
| the-sunken-temple | 32 | 59 | **3** | 18 | 39 | ok |
| the-serpent-vaults | 32 | 72 | 5 | 11 | 39 | ok |
| the-thornwood-trial | 32 | 35 | 4 | 9 | 21 | ok |
| the-labyrinth-of-glass | 32 | 59 | 6 | 10 | 34 | ok |
| the-sunspire-ascent | 24 | 26 | **2** | 9 | 16 | ok |
| the-smugglers-cut | 24 | 26 | 5 | 13 | 20 | ok |
| the-iron-spire-trial | 24 | 42 | 6 | 10 | 24 | ok |
| the-drowned-court | 29 | 30 | **2** | 6 | 17 | ok |
| the-cinder-bazaar | 29 | 33 | 10 | 10 | 19 | ok |
| the-red-meridian-run | 29 | 47 | 6 | 10 | 25 | ok |
| the-ashfall-expedition | 37 | 48 | 4 | 8 | 25 | ok |
| the-pale-road | 37 | 81 | 7 | 14 | 43 | ok |
| the-tenfold-siege | 37 | 37 | 8 | 12 | 24 | ok |

Two things follow, and the first retracts an earlier claim.

**The catalog is not shallow by construction.** Median negative-ending depth is 16 to 43 nodes. Those are
substantial reads on most paths, and PL-20 holds every winning path at 26 to 81 nodes against floors of 24 to
37. An earlier draft cited a uniform-random-walk mean depth of 4 to 9 nodes and implied the books deliver only
that. Both numbers are correct and they measure different things: the *distribution of endings by depth* is
deep, while a *probability-weighted random walk* exits early because a per-node fatal-branch hazard compounds
geometrically. Random walk is also a pessimistic proxy, since a real reader reads the prose and avoids
obviously fatal choices. The honest statement is that endings are mostly deep and that delivered depth is
simply unmeasured, which is what D16 exists to fix.

**The narrow, real gap is the one PL-20 declares out of scope: "Fail-fast negative endings are unaffected."**
The depth principle is enforced on the winning path and has no sibling rule on the fail path, so a tree can
satisfy a 29-node win floor while offering a terminal at node 2. Shortest fail runs at **7% to 17% of the win
floor**, and `the-sunspire-ascent` and `the-drowned-court` both terminate as early as node 2.

Sizing the remediation across all 1,778 endings in the 14 gamebook skeletons:

| Fail-depth floor | Endings below it | Share |
| --- | --- | --- |
| 25% of the cell's `min_complete` | 100 | 5.6% |
| 33% | 178 | 10.0% |
| 50% | 395 | 22.2% |

A floor at 25% to 33% is therefore **surgical, not a rebalance**: 100 to 178 endings out of 1,778, each
remediable by WS-5's M2 ending re-map, converting an early lethal terminal into a `setback` that routes back
into the graph. That is far cheaper and better targeted than the "rebalance the gamebook cells" an earlier
draft proposed, and it extends an existing, ratified design principle rather than inventing one.

**Why it is still a diversity finding.** The content that differentiates one 500-node tree from another lives
in its depth: the mid-game branches, the distinct set pieces, the payoff. A reader who exits in the first few
nodes has read only the shared opening funnel, so two structurally distinct gamebooks are indistinguishable to
them. The shallow tail is a small share of endings, but it is the share a reader hits first and hits
repeatedly across re-reads, which is exactly where perceived sameness forms. Closing it is cheap, and it
protects every other lever in this plan.

Separately, "few wins" still has no number: 2 to 5 winning endings out of 74 to 209 is unconstrained by any
rule. That remains a product decision for D18 to ratify, now independent of the depth question.

Note also that re-reading is a supported loop: `api/reading.py::list_completions` tracks "every ending a child
profile has completed" per profile, so ending-collection is expected. That is an argument for closing the
shallow tail rather than against it: every re-read that exits early re-reads the same opening funnel.

### 1.3 Expanding the curated vocabulary is the right fix, and it exposes a worse defect

Owner clarification (2026-07-25): the 12-tag map was a deliberate **baseline**, not a design limit, and
expanding it is on the table. That reframes D2 and it is the better path, because expanding a curated list
preserves every property section 1.1 had to defend: the vocabulary stays closed, stays echo-safe by
construction, stays free of premise substrings, adds no personal data at rest, and raises no DPIA question.
The open-vocabulary variant is now a fallback, not the plan.

**The expansion target is already authored.** The skeleton catalog declares **132 distinct curated themes**
across `metadata.themes` (`adventure`, `courage`, `friendship`, `grief`, `baking`, `music`, `codes`,
`astronomy`, `heist`, `investigation`, `belonging`, `fairness`, ...). **Zero of them are values in
`_THEME_TAG_MAP`.** So the story side of the comparison already speaks a 132-term curated vocabulary while the
request side can only recognise 12 tags. The controlled vocabulary this needs largely exists; it has simply
never been wired to the request side.

**And that asymmetry is a worse defect than the coverage gap.** `history.py` builds a stored entry's signature
as `theme_signature(brief, _themes_from_blob(blob))`: premise tags **union** the story's raw curated themes,
with `_THEME_TAG_MAP.get(lowered, lowered)` passing unmapped themes through verbatim. An incoming request has
no story yet, so its signature is premise tags only. The two sides are structurally unequal in size, and
symmetric Jaccard punishes exactly that. Measured:

```text
request sig : ['dragon', 'fire']
stored sig  : ['coming-of-age', 'courage', 'dragon', 'fire', 'friendship', 'mystery']
jaccard     : 0.333   tau_theme = 0.35  ->  NOT similar
```

**A byte-identical premise, on the same tree, does not register as similar.** The four curated themes the
request could never have produced sit in Jaccard's denominator and push a perfect match below the threshold.

This changes the severity of finding 3.1. The audit said WS-4 is inert for out-of-vocabulary themes; it is
closer to inert for **all** themes, because even the 12 tags that do fire get diluted on the stored side. Any
coverage work that does not also fix the measure will keep under-triggering.

**Two fixes, both cheap, and they compose:**

1. **Expand and unify the vocabulary (D2a).** Grow `_THEME_TAG_MAP` so the request side can emit the same
   controlled tags the catalog declares, and normalise `metadata.themes` **into** that vocabulary instead of
   passing raw strings through. Note that the 132 are not all usable as tags: some are per-story literary
   themes (`compromise as inheritance`, `conduct carried up the wall`) that belong in prose notes, not in a
   matching vocabulary. Curate a controlled set, roughly 60 to 120 tags, spanning relational themes,
   activity and domain, setting, companion or creature, and narrative mode.
2. **Stop using symmetric Jaccard for request-versus-story (D2b).** A request is a short statement of intent;
   a story carries a fuller theme set. Use a containment measure, `|A n B| / |A|` with `A` the request
   signature, or the overlap coefficient `|A n B| / min(|A|, |B|)`. The example above then scores 1.0 rather
   than 0.333. Add it as a new function: `jaccard_similarity` is also used for leaf distance, where symmetry
   is correct, so it must not change.

**Keep the review gate on any expansion.** The vocabulary is echo-safe *because* it is curated and
human-reviewed. Expansion must stay in reviewed code or reviewed data, never a runtime-learned or
auto-mined list, or "echo-safe by construction" quietly degrades to "echo-safe by hope".

### 1.4 The family-only versus catalog two-prong: sound, with one blocker and two caveats

Owner proposal (2026-07-25): let the guardian choose whether a book is family-only or added to the general
library, apply strict PII controls on the catalog path, and allow a less strict approach on the family-only
path. Evaluated against what is already built:

**The machinery exists.** `publishing/state_machine.py::Visibility` is a closed `FAMILY` / `CATALOG` enum,
`storybook.visibility` carries a check constraint, and `api/assignments.py` and `api/library.py` already gate
browse, assign, and read on it. A catalog book is cross-family assignable; a family book is not. Nothing needs
inventing.

**The risk-tiering instinct is correct.** The WS-7 echo renders a child's own request back to that child and
their own guardian, which is intra-family regardless of visibility. Showing a family their own words back is a
materially different exposure from publishing them to other families, and a proportionate, risk-based control
is a defensible design posture. A relaxation scoped to family-only is the right shape.

**Blocker: the flag does not exist yet when the strictness decision has to be made.** `Visibility` is
"chosen by the admin at release approval" (its own docstring) at the *end* of the pipeline. The theme signature
is derived at request time for selection, and the degraded interpretation and echo are produced at fill time.
Both happen long before any visibility value exists, so the pipeline cannot branch on it. The fix is to
capture **intended visibility at intake**, as a guardian field on the story request, and treat the
approval-time value as the authoritative final one. Without that field the two-prong design cannot be
implemented at all, whatever the policy says.

**Caveat 1: visibility does not gate the LLM provider.** Interpretation text re-enters downstream prompts
(cover art, repair), so a family-only book still exports premise-derived content to a third-party processor,
and `privacy-model.md` still carries an **open blocker** on whether OpenRouter's standard-retention or
zero-data-retention path applies. So family-only means "not shown to other families", not "stays in our
system". A relaxation justified as "the data never leaves the family" would be overstating it; the honest
justification is the narrower one about intra-family echo.

**Caveat 2: on the catalog path, decouple rather than scrub.** Redacting names out of free text is a losing
game, and a child's premise published cross-family is a disclosure of their personal expression even with
every proper noun removed. The cleaner control is to **not publish the family-facing artifacts at all** on a
catalog book: the WS-7 interpretation and echo stay family-scoped, and the catalog listing carries only
skeleton-derived and generated metadata (title, cover, themes, band, length). That is a structural guarantee
rather than a filter that has to be right every time.

**Sequencing note.** Two existing decisions bear on the catalog prong. ADR-016 makes the catalog the widest
ring of the three-ring social boundary, and `privacy-model.md`'s "If Shared Beyond Family" section states that
the current controls are calibrated for private family use, with COPPA and Kids Category compliance a Phase 7
launch blocker that is **not yet done**. So the family-only relaxation is available now; routing
child-premise-derived books into a cross-family catalog should wait on that compliance work regardless of what
the visibility flag permits.

**One recommendation on who decides.** The proposal moves the catalog decision to the guardian. Today an admin
makes it at release approval, which puts an independent reviewer on a cross-family disclosure decision.
Prefer **guardian opt-in as a precondition, admin approval retained as the gate**: the guardian expresses
intent at intake (which is also what unblocks the timing problem above), and the admin still decides whether
it actually enters the shared catalog. That keeps both controls and costs nothing.

### 1.5 The visibility authorization rule: guardian sets a ceiling, admin may only restrict

Owner direction (2026-07-25): the admin needs a lever, but it must never override a guardian's setting unless
it is *more* restrictive. Guardian chooses global, admin may choose global or family. Guardian chooses family,
admin cannot change it. Admin-created book, admin chooses freely.

That is a **monotone restriction rule**, and it has a clean formal shape. Order the two values by
permissiveness, `FAMILY < CATALOG`. Then the resolved visibility is a lattice meet:

```text
resolved = min(guardian_ceiling, admin_choice)
```

with the guardian's value acting as a ceiling the admin can lower but never raise. The admin-created case is
not a special case at all: an absent guardian means the ceiling is the top element, `CATALOG`, and the meet
leaves the admin free. One function, no branching on who created the book.

| Guardian ceiling | Admin may resolve to | Admin may NOT | Why |
| --- | --- | --- | --- |
| `catalog` (global) | `catalog` or `family` | n/a | Admin restricts; a reviewer can always narrow disclosure. |
| `family` | `family` only | `catalog` | The guardian's restriction is binding. This is the load-bearing case. |
| none (admin-created) | `catalog` or `family` | n/a | No guardian intent to honor; ceiling is the top element. |

**The default differs by initiator, and a single constant gets one of them wrong.** `StoryRequest` already
carries `initiator_role` in `('child', 'guardian', 'admin')`, derived from the authenticated principal and
marked `#CRITICAL: security` in `story_requests/service.py`, so it is the right discriminator:

- `initiator_role` is `guardian` or `child`, and no explicit choice was made: ceiling is **`family`**. Silence
  is not consent to cross-family disclosure.
- `initiator_role` is `admin`: ceiling is **`catalog`**, meaning unconstrained, since there is no guardian
  whose intent is being honored.

**A child must never set the ceiling.** Per ADR-015 a child-initiated request is gated by a guardian, so the
ceiling is captured at that gating step, defaulting to `family`. Because `initiator_role` is derived from the
authenticated principal rather than supplied by the client, a child cannot present as a guardian to raise it.
The ceiling field must follow the same derivation, not accept a role from the request body.

**This rule turns the current `ApproveBody` default into a silent downgrade.** `ApproveBody.visibility`
defaults to `"family"` today, which is the safe default while the admin is the sole decider. Under the ceiling
rule, an admin approving a guardian-`catalog` book with no body would silently restrict it to family and look
like a deliberate decision. The omitted-body semantics must change from "family" to "honor the guardian
ceiling". That is a wire-contract change, so the generated frontend client has to be regenerated with it.

**Four decisions the rule implies but does not settle:**

1. **Can a guardian raise their own ceiling later?** It is their family's book, so yes in principle, but only
   through the guardian surface and never through the admin approve path, or the lever becomes a loophole. If
   the book is already published as `family`, raising the ceiling should re-enter review rather than widen
   disclosure in place.
2. **Post-publish restriction.** Restricting a published `catalog` book to `family` is more restrictive, so the
   rule permits it, and it is exactly what a takedown needs. But other families may already hold assignments.
   Recommend the restriction revoke cross-family assignments (the honest reading of "more restrictive") and
   that reading state be retained rather than deleted, so a re-widening does not lose a child's progress.
3. **Multi-guardian families.** If two guardians set different ceilings, take the **most restrictive**. Safe,
   predictable, and consistent with the rest of the rule.
4. **Dual-role adults.** `/v1/me` returns a base `role` plus an orthogonal `is_admin`, so one person can be
   both. Enforce the lattice on the **role being acted in**, not on identity: an adult who is both must raise
   their own family's ceiling on the guardian surface, not sidestep it via the admin path. Otherwise the admin
   lever is a hole in the guardian control for exactly the families where both hats are worn, which is most of
   them in a homelab deployment.

**Enforcement location.** In `publishing`'s approve service, not only in the API layer, and as a pure function
over a frozen table in the style of `state_machine.LEGAL_TRANSITIONS`. That keeps it unit-testable without a
database and gives one place to point at when asking whether a loosening is possible.

### 1.6 Ceiling changes and dual-role enforcement: both settled

Owner decisions (2026-07-25): a guardian **may** change the ceiling later, as long as it does not violate
privacy restrictions; and for dual-role adults the lattice is enforced on **the role being acted in**.

**What "does not violate privacy restrictions" actually amounts to: less than expected.** Checking whether any
content screen is keyed on visibility, the answer is that none is, and the screens already run at the stricter
setting:

- **Self-naming is disallowed by design, at every visibility.** `story_requests/interpretation.py` sets a
  self-naming request aside as `IDENTITY_PROTECTION` under Route A, and `generation/worker.py` notes that Route
  A "forbids ANY family requested family-child name". So a family-only book does not contain the requesting
  child's own name to begin with; there is no name to newly disclose by widening.
- **The PII egress floor and echo screens are visibility-independent.** `_echo_floor`'s four ordered checks
  (structural injection, graphic-echo minimum, `assert_prompt_pii_safe` against `PiiContext`, plus the
  unconditional email/phone/address patterns) take a band, never a visibility.
- **`moderation/rescreen.py` says so outright:** "this sweep does not filter on `Storybook.visibility`:
  'family-tier' and 'the current published catalog' are the same set today."

So a guardian widening needs **no content re-screen**. That is the useful finding: the natural design instinct
here is a re-screen gate on widening, and it would be redundant work, because the content was already screened
at the strictest level. Widening is a disclosure-surface change, not a content change.

**What widening does require:**

1. **D29's exclusion must be evaluated at read time, not baked at publish time.** If the catalog read surface
   filters out the family-facing WS-7 interpretation and echo by checking `visibility` when serving, then
   widening is automatically safe the moment the flag flips. If instead publish-time code decides which fields
   to persist for cross-family consumption, a later widening would expose family-facing artifacts that were
   written under the family-only assumption. This is the single load-bearing implementation requirement of the
   whole ceiling-change decision, and it is a test, not a feature.
2. **The Phase 7 COPPA gate still applies** (D31). A guardian may widen; that does not bypass the unfinished
   compliance work for cross-family distribution.
3. **An informed, deliberate action.** The guardian surface must state what becomes visible to other families.
   A book already read by another family cannot be unread, whatever the flag says afterwards.
4. **An explicit, audited, human-invoked path.** ADR-005 governs *both* directions of the publish decision, and
   `state_machine.LEGAL_TRANSITIONS` has no machine-reachable transition out of `published`. Visibility is a
   `Storybook` column rather than a status, so a post-publish change is not a status transition and would
   otherwise be a bare field update. It is a disclosure decision and needs the same audit trail as the original
   (D28). Open: whether widening a published book should additionally require re-approval, or whether the
   guardian's own action is sufficient given that no content changes.

**Correction to an earlier statement.** A previous turn of this analysis said narrowing "cannot reach offline
copies". That is wrong. `frontend/src/offline/revocation.ts::reconcileOfflineCache` already purges revoked
books from IndexedDB, deletes the associated reading state, and **drops** queued offline writes for a revoked
book rather than flushing them first. So revocation does reach offline caches on the next reconcile. The only
residual gap is a device that never comes back online. Narrowing is therefore more effective, and widening
correspondingly less irreversible, than stated earlier.

**Dual-role enforcement: the role being acted in.** The primitive already exists:
`story_requests/service.py` derives `initiator_role` from `principal.acting_role(family_id)`, so
`resolve_visibility` can be evaluated against the acting role rather than against identity or capability. The
consequence is deliberate friction: an adult holding both guardian and admin for their own family must raise
their own family's ceiling on the guardian surface, because the admin path can only restrict. In a homelab
deployment where one adult wears both hats, that is a two-step rather than a toggle, and that is the point:
the guardian control stays a real control rather than something the admin lever can quietly route around.

**Incidental docs gap.** `story_requests/interpretation.py` cites
`coppa-gdpr-remediation-plan.md Section 5 Decision 4` as the governing decision for Route A self-naming
policy, and that file is not present in `docs/planning/`. A security-relevant decision is currently governed by
a document that cannot be read. Restore it or repoint the citation.

### 1.7 PL-22's fraction: 33%, and the reasoning is measurable

Three candidate fractions, evaluated against the constraints that actually bear on the choice.

**Is there guidance in the initial research?** No. Searching `docs/planning/`, `docs/planning/adr/`, and
`docs/architecture/` for difficulty, frustration, discouragement, early-death, or forgiveness guidance returns
nothing on this question. ADR-011 sets terminal *fraction* ("~25-35% of nodes are terminals") and the
"few wins + many fails" character, and PL-20 sets the winning-path floor. How early a reader may be
terminated, and how many winning arcs there should be, are genuinely unspecified rather than specified
elsewhere and missed. So this is a decision to make, not a decision to look up.

**Constraint 1: the ending-count floor does not discriminate between 25% and 33%.** Converting an early
terminal into a routing `setback` removes an ending, and both the band `min_endings` and the breadth-scaled
gamebook ending fraction still have to hold. Measured headroom per skeleton:

| PL-22 fraction | Endings affected | Share of 1,778 | Skeletons breaking the ending floor |
| --- | --- | --- | --- |
| 25% of `min_complete` | 100 | 5.6% | 1 (`the-ashfall-expedition`) |
| 33% | 178 | 10.0% | 1 (`the-ashfall-expedition`) |
| 50% | 395 | 22.2% | **10 of 14** |

So 50% is confirmed as a genuine rebalance and should be rejected. 25% and 33% cost the same single exception,
which means the floor constraint is silent between them. And that exception is avoidable by construction:
**remediation must be ending-count-preserving**, relocating a terminal deeper (M2 ending re-map, or re-targeting
the choice that reached it) rather than deleting it. `the-ashfall-expedition` has zero headroom at either
fraction and so *must* relocate; everywhere else it is the better default anyway, because deleting endings
erodes the "many fails" character the fraction exists to preserve.

**Constraint 2: the shared opening funnel, which is what the diversity argument actually rests on.** PL-22
exists so a reader gets past the shared opening before terminating, since a reader who exits inside the funnel
has read nothing that distinguishes this tree from another. So the floor should clear the depth at which the
tree's distinctive content becomes reachable. Using "BFS depth at which 10% of the tree is reachable" as that
proxy:

| Measure | Median | Range |
| --- | --- | --- |
| Depth at which 10% of the tree is reachable | **9** | 6 to 12 |
| 25% of `min_complete` | 8.0 | 6 to 9 |
| 33% of `min_complete` | 10.6 | 8 to 12 |

Per skeleton, **33% clears the 10%-reachable depth in 13 of 14; 25% clears it in only 3 of 14.** A 25% floor
lands just inside the funnel region, which is precisely the failure PL-22 is meant to prevent. A 33% floor
lands just past it.

**Recommendation: 33%.** It is the smallest fraction that satisfies the rule's own rationale, it costs the same
single ending-floor exception as 25%, and 178 relocations across 14 skeletons is a bounded, mechanical job.
Choosing 25% would ship a rule that passes its own test on 3 of 14 trees, which is worse than not having the
rule, because it would read as solved.

**One exception to note.** `the-smugglers-cut` has a 33% floor of 8 but reaches 10% of its tree only at depth
11, so it still permits an exit inside its funnel. The per-cell table should therefore allow a per-cell
override where the funnel is unusually deep, rather than treating 33% as universal. Defining PL-22 as
`max(0.33 * min_complete, funnel_clearing_depth)` is the more principled form; start with the constant, and
promote to the max form if D16's telemetry shows funnel exits still matter.

**Resolved: the 60% tense-but-fair question.** Accepted per owner review. A cell holding one ~95% gauntlet, one
~80% harsh-but-survivable, and one ~60% tense-but-fair is legitimate gamebook variety rather than a broken
`narrative_style` promise. D19 moves from "hold pending telemetry" to accepted, and the in-cell outcome-spread
requirement is a design target rather than an open question. `narrative_style` continues to promise the
gamebook *form* (second person, gauntlet-capable topologies, many fails), not a specific lethality rate.

### 1.8 The request page must state the restrictions before the child invests in an idea

Owner direction (2026-07-25): if we block a child from using their own name and never said so on the request
page, they will be annoyed that the book did not turn out as expected. That is correct, and there is a
structural reason it cannot be fixed after the fact.

**What the request surface says today.** `frontend/src/library/RequestStory.tsx` renders one prompt, "What
should your story be about?", a 500-character textarea, and an optional series name. It states **no
restrictions at all**. A child can type "a story where I'm the hero and my name is Maya" with no indication
that neither part of that will happen.

**Why the WS-7 echo cannot cover this.** WS-7 reflects the interpretation back after submission, which is the
right mechanism for "here is what we built and what we set aside". But `interpretation.py` defines
`_ELEMENT_MUST_BE_NULL` over exactly three reason codes, `SAFETY_POLICY`, `PERSONAL_DETAILS`, and
`IDENTITY_PROTECTION`: for these, the offending phrase "is never echoed, stored, or paraphrased". So for the
three most surprising restrictions, including self-naming, the post-hoc reflection can name the *reason* but
structurally cannot show the child *what* it dropped. Pre-submission disclosure is therefore not a nicety
duplicating the echo; it is the only place the expectation can actually be set.

**The authoritative restriction set.** `ReasonCode` has ten members, six of which are requester-facing
restrictions worth stating up front:

| Reason code | What to tell the requester |
| --- | --- |
| `IDENTITY_PROTECTION` | The hero will not be you. Self-naming is disallowed by design (Route A). |
| `PERSONAL_DETAILS` | No real names, addresses, phone numbers, or emails, yours or anyone's. |
| `STRUCTURE_FIXED` | How many endings there are, where they are, and how the story branches are already set and cannot be requested. |
| `BAND_POLICY` | Some content is off-limits for this reader's age band. |
| `GUARDIAN_CONTROL` | This family has some themes turned off. |
| `SAFETY_POLICY` | Some phrasings are withheld by the safety floor. |

The remaining four are not restrictions: `BOUND_TO_SLOT` and `STORY_FIT` are successes, `NOT_THIS_STORY_KIND`
and `NO_CONFORMING_BINDING` are fit outcomes that only exist after a bind attempt.

**Design requirements:**

1. **Derive the copy from the enforcement source, not from hand-written strings.** A hard-coded list on the
   request page will drift from `ReasonCode`, `band_profile`, and the guardian's `content_nogo` the first time
   any of them changes, and a stated restriction that no longer matches behaviour is worse than none. Serve
   the restriction set from the API, keyed on the requesting profile's band, so the page renders what the
   pipeline will actually enforce.
2. **Band-appropriate copy.** The `AgeBand` is known at request time. A 3-5 requester and a 16+ requester need
   different wording for the same rule, and the kid surface needs the positive framing ("your hero gets a
   made-up name") rather than the policy framing.
3. **Resolved (owner decision, 2026-07-25): the kid surface says only that some themes are off.**
   `GUARDIAN_CONTROL` reflects that family's own banned themes, and naming them to a child exposes guardian
   intent, so the kid surface states the fact without the list. The guardian surface shows the actual list,
   which the guardian set and can change. Two things follow for implementation: D36's API response must not
   carry the `content_nogo` values on the kid-surface variant at all, rather than sending them and relying on
   the client not to render them, and the kid-facing copy must not vary with the list's contents, since copy
   that changes when a theme is added leaks the list one bit at a time.
4. **Serves [K19](capability-register.md)** (expectation-setting) as its pre-submission half, alongside WS-7's
   post-submission reflection. Worth recording as such so the two are maintained together.

### 1.9 "How many winning arcs" is the wrong question: it is path mass, not ending count

Owner direction (2026-07-25), resolving the last open product decision:

- A gamebook may have **more than one** successful outcome.
- For a **series**, every end point must allow for a **single start point** in the next book.
- The minimum should be **a reflection of the branching strategy**, not a fixed number.
- Reconvergence is fine: many nodes collapsing to a couple of final paths, or several paths all reaching one
  successful ending, is acceptable.
- But **ten positive endings where 90% of paths reach a couple of unsuccessful ones does not work.**

That last clause invalidates D18 as drafted. A `min_positive_endings` count scaling with ending count would
have passed a book with ten unreachable wins and failed a book with one well-fed win, which is backwards. The
constraint is on **the distribution of path mass across endings**, and the count of positive endings should be
left entirely unconstrained.

**The failure case is already in the catalog.** Choice-uniform walk, 40,000 trials per skeleton. `SPM` is
satisfying path mass, the share of playthroughs reaching a `success`/`completion` ending; `top2`/`top5` are the
share of terminal mass absorbed by the most-hit 2 and 5 endings; `reached` is how many distinct endings were
ever hit:

| Skeleton | Endings | Positive | SPM | top2 | top5 | Reached |
| --- | --- | --- | --- | --- | --- | --- |
| the-drowned-court | 105 | **5** | **0.00%** | 38% | 75% | 43 |
| the-harrowstone-keep | 152 | 4 | 0.01% | 38% | 57% | 136 |
| the-thornwood-trial | 115 | 4 | 0.00% | 50% | 85% | 48 |
| the-serpent-vaults | 172 | 4 | 0.00% | 29% | 72% | 40 |
| the-ashfall-expedition | 143 | 3 | 0.00% | 40% | 70% | **30** |
| the-tenfold-siege | 209 | 2 | 0.00% | 29% | 71% | 54 |
| the-smugglers-cut | 80 | 2 | 0.50% | 50% | 76% | 62 |

`the-drowned-court` is the described failure exactly: **five positive endings, and effectively no path mass
reaches any of them**, while the top five endings absorb 75%. Ending count and path mass are fully decoupled,
which is why the count is the wrong lever.

**A third finding falls out of the `reached` column.** Only 30 to 136 of each book's declared endings are ever
hit in 40,000 walks: `the-ashfall-expedition` reaches 30 of 143, `the-tenfold-siege` 54 of 209. The
breadth-scaled `min_endings` floor counts **declared** endings, so ADR-011's terminal-fraction guarantee is
satisfied in part by endings a reader will essentially never see. Declared ending count overstates delivered
variety, and any future ending-count floor should prefer mass-bearing endings.

**The formalization, replacing `min_positive_endings`:**

1. **A satisfying-path-mass floor, keyed on topology.** "A reflection of the branching strategy" is directly
   implementable: `structure_features().topology` already classifies every tree as `gauntlet`,
   `branch_and_bottleneck`, `sorting_hat`, `open_map`, `time_cave`, or `loop_and_grow`. A `gauntlet` earns a
   lower SPM floor than a `sorting_hat` by design. The floor is per topology, not per cell and not a constant.
2. **Concentration is explicitly permitted.** Reconvergence to few endings is fine, and one satisfying ending
   absorbing all winning mass is fine. The rule fails only when the *satisfying* share falls below the floor.
   No rule should penalize a low ending count or a high top-k share on its own.
3. **Positive ending count stays unconstrained.** Deliberately: it is the measure that produced the wrong
   answer.

**Caveat on the model.** Choice-uniform walk is a structural lower bound, not a prediction: a real reader reads
the prose and avoids obviously fatal choices, and condition-gated choices mean some sampled paths are ones a
real reader could not take. So structural SPM is a **design gate**, and the floor must be calibrated against
the real satisfying-ending rate from D16's telemetry rather than set from the model alone.

### 1.10 The series rule exposes two validator gaps and one design tension

"Every end point must allow for a single start point in the next book" is stronger than what SR-5 enforces, and
checking it found two gaps.

**What SR-5 does today.** Its docstring: "each non-final book has a win ending and a next-book entry node...
It does NOT trace that the win ending targets that entry node; books are independent graphs with no shared node
ids." So it verifies that *a* win exists and that the next book declares a `series_entry_node`. It says nothing
about the other 148 endings.

**Gap 1: endings that foreclose continuation are permitted in a non-final book.** `death` and `capture` are
states you cannot continue a campaign from, yet nothing forbids them in a book that promises a sequel. The
catalog's only series, `brass-lantern`, is exactly this case:

| Book | Skeleton | Endings | death | capture | Foreclosing | Satisfying |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | the-harrowstone-keep | 152 | 17 | 77 | **94 (62%)** | 4 |
| 2 | the-sunken-temple | 152 | 17 | 77 | **94 (62%)** | 4 |

62% of each book's endings cannot lead to the next book's `n_start`. Both books do use a single
`series_entry_node` of `n_start`, so the single-start-point convention is already followed; it is the endings
that do not honor it. The machine-checkable part of the owner's rule is therefore a new rule, **SR-8**: in a
non-final series book, no ending may be of a continuation-foreclosing kind. `death` is unambiguous; whether
`capture` forecloses or is a legitimate cliffhanger ("you are taken, and book 2 opens in the cell") is a
narrative decision to settle before SR-8 lands.

**Gap 2: nothing requires the highest-index book to be final.** SR-4 flags a book *below* the highest index
that is `is_final`; SR-5 skips the highest index entirely. So `brass-lantern` book 2, declaring
`is_final: false` with no book 3 in the catalog, passes both. A chain can promise a continuation that does not
exist, and a reader finishes book 2 expecting book 3. That is **SR-9**: the highest-index book must be
`is_final`, or a successor must exist.

**The design tension, worth recording.** A gamebook wants many fails; a series requires every ending to be
continuable. So series-plus-gamebook is a genuinely constrained combination: its fails must be `setback`-shaped,
survivable and continuable, rather than `death` or `capture`. `brass-lantern` reads as authored gamebook-first
and series-second, which is how it acquired 94 foreclosing endings.

**This composes with PL-22.** D17's remediation converts early terminals into routing `setback`s, and SR-8's
remediation converts foreclosing terminals into continuable ones. Both are M2 ending re-maps in the same
direction, so the two jobs should be done in one pass over the affected skeletons rather than twice.

### 1.11 Root cause: `restart-on-fail` is specified, half-built, and unrepresentable

Owner expectation (2026-07-25): in a gamebook, many paths should be **setbacks**, not end-of-story-and-start-over.

That is what ADR-011 specifies, and tracing why the catalog does not do it found the root cause of every P4
symptom.

**ADR-011 defines `restart-on-fail` as a first-class flow primitive.** Its flow-primitive list reads:
"**restart-on-fail** (negative ending -> start/checkpoint)". The per-band allowance table grants it as
"yes, lethal (gamebook)" for 13-16 and 16+. And it is written into the definition of the `gauntlet` topology
itself: "linear spine, branch-to-fail, terminal (many), **restart-on-fail**", whose reread driver is
"master the one path". A gauntlet is *supposed* to be many terminals plus a loop back, so the reader learns the
route across attempts.

**The schema forbids the edge that would implement it.** `storybook/models.py`'s `Node` validator:

```text
if self.is_ending:
    if self.choices:
        msg = f"ending node '{self.id}' must have no choices"
```

An ending node has no outgoing edge, by invariant. So "negative ending -> start/checkpoint" is unrepresentable
in an authored graph. Grepping the source for `restart` finds worker restarts, Redis restarts, and Kubernetes
probes: the primitive appears nowhere in the implementation.

**And the checkpoint half is built but has no producer.** `player/state.py` carries
`save_slots: dict[str, Snapshot]`, and `engine.py::_clone` copies each snapshot individually with a documented
purity guarantee so "a cloned timeline cannot mutate a save slot shared with the original". `replay.py` already
reconstructs a state from a `choice_path`, so state restoration works. But `EffectOp` operates on variables
only (`var: str`), there is no save-slot effect, the strings `save` and `slot` do not appear in
`storybook/models.py`, and no API exposes slots. **`save_slots` is correct runtime plumbing that nothing can
ever write to.**

**So the chain is:** ADR-011 specifies restart-on-fail; the schema cannot express it; the checkpoint mechanism
has no producer; therefore all 1,778 gamebook terminals are hard stops, and the gauntlet topology's defining
reread loop has no in-product mechanism at all. That is why SPM is ~0%, why an early terminal costs the whole
session rather than a few nodes, and why only 30 of 143 endings are ever reached.

**Two designs, and the tension between them resolves cleanly.**

*Design A, the non-terminal setback (the literal reading of the owner expectation).* Model a setback as an
ordinary node: an `on_enter` penalty effect plus choices routing onward. **Expressible today with no schema
change**, which is worth knowing: authors simply used `is_ending: true, kind: setback` instead. But it collides
with ADR-011's terminal fraction. `the-thornwood-trial` has 111 setback terminals out of 115 endings against a
`min_endings` floor of 94, so converting even 22 of them breaks the floor. Wholesale conversion is not viable;
targeted conversion of the shallowest terminals is exactly what D17 already does.

*Design B, restart-on-fail via checkpoints (what ADR-011 intended).* Keep terminals many, and make a terminal
not the end of the **session**. Needs three pieces: a way to establish a checkpoint (a new effect op, or an
implicit checkpoint at bottleneck nodes), a restart affordance offered at an ending in the API and reader UI,
and authored checkpoint placement. Two of the three hard parts already exist in `save_slots` and `replay.py`.

**Design B is primary, A is the targeted supplement.** B preserves ADR-011's terminal fraction and the "many
fails" character while restoring the loop the framework assumes, and it is the design the ADR actually
specifies. A stays useful for the shallowest terminals under D17.

**Two consequences for deliverables already in this plan:**

1. **D18's SPM measure changes shape.** With restart-on-fail, a per-walk satisfying path mass near zero is not
   necessarily a defect: the meaningful measure becomes the **cumulative satisfying rate per session**, across
   restarts. The structural per-walk SPM stays useful as a design gate, but the floor must be set against
   session-level telemetry (D16), not against the single-walk model.
2. **Checkpoint placement and PL-22 are the same measurement.** A restart that returns the reader to node 1
   makes them re-read the shared opening funnel, which is precisely the diversity failure PL-22 exists to
   prevent. So checkpoints must sit at or past the funnel-clearing depth, which is the same 33%-of-`min_complete`
   quantity section 1.7 derived. One number serves both rules.

### 1.12 The two-tier restart model, and the three things it simplifies

Owner design (2026-07-25):

- **Setback:** loop back automatically to a previous safe point, a node where the reader can choose a different
  path.
- **Terminal ending:** offer the reader a choice, restart from the last safe point **or** restart from node 1.
  Especially important for series books.

This is a better model than section 1.11 recorded, and it resolves three things that were open or wrong.

**It answers D46: the safe point is derivable from the reader's own state, not authored.** "A safe place where
they can choose a different path" is a precise definition: the most recent visited non-ending node with more
than one visible choice, where at least one choice from it remains untaken. `ReadingState` persists `path` (the
ordered node ids), `var_state`, `visit_set`, and `save_slots`, so the engine can identify it without any help
from the author. So the checkpoint mechanism needs **no new `EffectOp`, no authored marker, and no
implicit-at-bottleneck heuristic**: the engine writes a snapshot as the reader passes a qualifying safe point.
`save_slots` finally gets its producer, and the producer is the runtime rather than the story. That is almost
certainly what it was built for.

**One implementation constraint makes the snapshot approach mandatory rather than optional.** `choice_path` is
**not** persisted on `ReadingState`; only `path` is. So a rewind cannot reconstruct historical `var_state` by
replaying choices: when two choices from one node share a target but carry different `effects`, the taken choice
is not recoverable from the node sequence alone, and reconvergent gamebook graphs do exactly that. Snapshots
avoid the problem entirely by storing the state rather than re-deriving it.

**It removes the need for any schema change or catalog remediation for setbacks.** A setback ending stays
`is_ending: true` in the graph; the player auto-returns the reader to the safe point. The terminal-fraction
floor is untouched, ending counts are untouched, and `the-thornwood-trial`'s 111 setback terminals are fine
exactly as authored. Design A from section 1.11 is therefore not needed as a catalog change at all: it is a
player behaviour.

**It narrows PL-22 from 178 endings to 73.** Only a *foreclosing* terminal leaves the reader with a restart
decision; a setback returns them automatically at negligible cost. So PL-22 should apply to `death` and
`capture` terminals, not to setbacks. The shallow tail below 33% of `min_complete` splits:

| Kind | Endings below 33% | Share | PL-22 applies? |
| --- | --- | --- | --- |
| `setback` | 104 | 58% | No, the auto-loop handles them |
| `death` / `capture` | **73** | 41% | Yes |
| other | 1 | 1% | Case by case |

**And that makes the ending-floor problem disappear.** Section 1.7 flagged `the-ashfall-expedition` as the one
skeleton with zero ending-count headroom at either candidate fraction. All 29 of its shallow terminals are
`setback`, so it needs **zero** conversions. Re-checking every skeleton with PL-22 scoped to foreclosing
terminals only: no skeleton falls below its `min_endings` floor. The "remediation must be ending-count-preserving"
constraint from section 1.7 is no longer forced by arithmetic, though it remains the better default.

**It answers D42 and retracts SR-8.** Section 1.10 flagged `brass-lantern`'s 94 `death`/`capture` endings per
book (62%) as a series-continuity violation. **With restart-on-fail available, that is not a defect.** A
foreclosing terminal no longer forecloses the *series*; it forecloses that *attempt*. The reader restarts from a
safe point or node 1 and can still reach the continuable ending, which SR-5 already requires to exist. So:

- SR-8 as drafted (forbid continuation-foreclosing ending kinds in a non-final series book) is **not needed**.
  The property that matters is that restart-on-fail exists, which is a product invariant rather than a graph
  property, so there is nothing for the validator to check.
- D42 ("does `capture` foreclose continuation?") is **resolved: neither `death` nor `capture` forecloses**,
  given restart. Both foreclose an attempt.
- `brass-lantern` needs no ending remediation on continuity grounds. It still needs the D9 clone resolution and
  whatever PL-22 requires of its foreclosing terminals, which for these two skeletons is zero, since all 12 of
  each book's shallow terminals are `setback`.
- **SR-9 stands unchanged.** Nothing about restart fixes book 2 declaring `is_final: false` with no book 3.

**One new open question, and it is live.** For a state-carrying series (`carries_state: true`, which
`brass-lantern` is), what does "restart from node 1" mean for state inherited from the previous book? It should
**not** reset that state, since the reader earned it in book N-1; node 1 should mean this book's start node with
the inherited state intact, and only this book's own progress discarded. The API needs to distinguish
"book-local reset" from "series reset", and offering the latter to a reader at all is a product decision.

### 1.13 Opt-in challenge mode: permadeath as a campaign reset

Owner direction (2026-07-25): in gameplay style, killing the character would traditionally send the reader back
to book 1, node 1. That should be something a reader can **opt into** to increase the complexity if they wish.

This adds a third tier above section 1.12's two: with the mode enabled, a `death` ending resets the whole
series rather than returning the reader to a safe point. Opt-in, never default.

**The band gate comes free from existing policy.** No new rule is needed to decide where this may be offered:

| Band | `forbidden_ending_kinds` | ADR-011 restart-on-fail | Challenge mode offerable? |
| --- | --- | --- | --- |
| 3-5, 5-8 | `death`, `capture` | none / soft try-again only | No: there is no `death` ending to trigger it |
| 8-11 | `death` | failure/entrapment, no death | No: same reason |
| 10-13 | none | "yes, logical" | No: `death` exists but lethal restart is not sanctioned |
| 13-16, 16+ | none | **"yes, lethal (gamebook)"** | **Yes** |

ADR-011 already says restart-on-fail is "lethal only from `13-16` up", and the two lower bands have no `death`
ending for the mode to act on. So the mode is offerable at 13-16 and 16+ and nowhere else, derived from policy
already in place.

**It resolves section 1.12's open question by contrast.** There are now two distinct resets, and they are not
the same operation:

- **Book-local node-1 restart** (section 1.12, the normal-mode option on a foreclosing terminal): returns to
  *this book's* start node and **preserves** state inherited from book N-1, which the reader earned there.
- **Series reset** (this section, the challenge-mode consequence of `death`): returns to **book 1, node 1** and
  discards carried state.

So a series reset is a *consequence the reader opted into*, not a menu item offered casually. That is a better
answer than offering both resets side by side, and it closes the question 1.12 raised.

**Nothing exists to hold the mode flag.** There is a catalog-level `Series` table, but **no per-profile series
progress table**: series progress is implicit in the per-book `ReadingState` rows plus `Completion` rows, and
`get_series_next` resolves the next book on demand each time. So this feature needs one new per-(profile,
series) row to carry the mode. That is the only schema addition it requires, and it is worth noting that it also
gives series progress a home it currently lacks.

**A series reset is a multi-row destructive operation, and that is the risky part.** It resets every
`ReadingState` row for that profile across the series' books. Three requirements follow:

1. **Atomic and server-authoritative.** It must not be applied optimistically on-device. A death that happens
   offline and arrives through `offline/sync.ts` could otherwise destroy a run during conflict resolution, and
   resolving that conflict wrongly costs the reader hours rather than minutes.
2. **`Completion` rows must survive.** `api/reading.py::list_completions` tracks "every ending a child profile
   has completed" as an achievement log, not as progress. A permadeath reset should clear reading state and keep
   the collected endings, or the mode punishes the reader twice and erases the collection loop that makes
   re-reading worthwhile.
3. **It must interact correctly with `state_revision`** optimistic concurrency across every affected row, not
   just the book the death occurred in.

**Mode locking is a genuine decision.** If a reader can switch to normal mode after dying, the challenge is
void; if they are locked in, a child can be trapped in an experience they no longer want. Recommend: allow a
downgrade from challenge to normal at any time, but never retroactively undo a death that has already reset the
run. The consequence stands, the mode does not trap them.

**Guardian visibility.** A mode that destroys hours of progress is worth surfacing to the guardian, consistent
with the existing G-series controls: reader-selectable, band-gated, guardian-visible. Whether a guardian can
withdraw availability is a product decision rather than a safety one.

**State the consequence before opt-in.** This is section 1.8's principle applied to a new surface: "if your
character dies, you start again at the very beginning of book 1" must be stated plainly at the point of
enabling, not discovered on the first death. Unlike the request-page restrictions, this one *can* be explained
afterwards, but by then it has already cost the reader the run.

**One honest tension with the diversity objective.** Challenge mode increases replay volume, which surfaces more
distinct leaves; but it also forces repeated re-reading of the shared opening funnel, which is exactly the
perceived-sameness failure PL-22 exists to prevent. For a mode the reader deliberately chose, that trade is
acceptable. It is another reason the mode must never be the default, and it raises rather than lowers the value
of D48's checkpoint placement for normal mode.

---

## 2. Objective and constraints

Objective is unchanged from [story-flexibility-plan.md](story-flexibility-plan.md) section 1: minimise the
perceived similarity between any two stories a reader encounters. This plan adds one clause the audit made
necessary: **and ensure the reader actually reaches the content that differentiates them.**

Constraints every deliverable holds:

1. The ADR-011 constraint grammar stays frozen. No deliverable requests a safety exception, and none should be
   granted one.
2. Every generated story passes the full `validator/` gate and `moderation/` review before publish.
3. The novelty floor: selection never fully excludes an eligible candidate. Every weighting change keeps the
   `1/(1 + ...)` form.
4. **New: no diversity mechanism may create, persist, render, or export personal data that the system does not
   already hold for the story-generation purpose.** This is the generalisation of section 1.1 and it binds
   D1-D4 and D11.
5. The WS-7 echo path is byte-identical after D1. A privacy-motivated refactor that changes what a child sees
   has failed.

---

## 3. Phases and deliverables

Six phases. P1 and P2 are prerequisites for trusting any diversity metric and should land first. Effort is
S (under a day), M (a few days), L (a sprint or more).

### P1: Unblock the similarity signal (findings 3.1, sections 1.1 and 1.3)

Nothing downstream of similarity works until this lands. Revised per section 1.3: **expanding the curated
vocabulary is the primary path**, and the open-vocabulary variant drops to a fallback. D2 and D3 are the two
that actually turn the signal on, and neither changes the privacy posture at all.

| ID | Deliverable | Effort |
| --- | --- | --- |
| D1 | Split `theme_signature` into `echo_signature` (today's function, renamed, behaviour byte-identical) and `similarity_signature`. Repoint `worker.py`'s two degraded-interpretation call sites at `echo_signature`; repoint `history.py` and `query.py` at `similarity_signature`. Pure refactor, no output change. Worth doing even though D2 keeps both closed: it names the echo-safety requirement so a later coverage change cannot silently widen the rendered surface. | S |
| D2 | **Expand and unify the controlled vocabulary.** Grow `_THEME_TAG_MAP` so the request side can emit the tags the catalog already declares, and normalise `metadata.themes` *into* that vocabulary rather than passing raw strings through. Curate roughly 60-120 tags from the 132 themes the catalog declares, dropping the per-story literary phrases that are not matchable tags. Stays closed, stays echo-safe, stays reviewed: no new personal data, no DPIA question. | M |
| D3 | **Replace symmetric Jaccard for request-versus-story comparison.** Add a containment measure (intersection size over the *request* signature's size, or the overlap coefficient over the smaller of the two) and use it in `score_history`. Leave `jaccard_similarity` untouched: leaf distance needs symmetry. This alone lifts the worked example in section 1.3 from 0.333 to 1.0. | S |
| D4 | Make "unknown" distinct from "dissimilar". `jaccard_similarity(frozenset(), frozenset())` returns `0.0`, so an unrecognised theme is affirmatively scored as maximally dissimilar to a byte-identical prior request. Return an explicit unknown and have `score_history` treat it **conservatively** (assume similar), so the failure mode is over-diversifying rather than silently disabling. | S |
| D5 | Re-derive `tau_theme`. The 0.35 threshold was set against a 12-tag symmetric-Jaccard space; D2 and D3 change both the vocabulary size and the measure. Re-fit on the D6 panel and record the new value with its basis. | S |
| D6 | A committed evaluation panel of realistic premises (pets, sports, family, school, music, invention, weather, food, sibling relationships) paired with catalog themes, so coverage and threshold claims are testable and regression-gated in CI alongside the existing WS-0 panel. | S |
| D7 | **Fallback, do not build yet:** an open-vocabulary `similarity_signature` (`content_tokens(mask_tokens(premise, extract_entities(...)))`, never rendered, persisted, or prompted) plus the `privacy-model.md` entry and DPO review from section 1.1. Build only if D2 plus D6 show coverage still short of target, and only behind the D1 split. | M |

**Acceptance.** On the D6 panel, over 95% of realistic premises yield a non-empty signature; two paraphrases of
one request score above the re-derived `tau_theme`; and a byte-identical premise against a stored story with
curated themes scores as similar (today it scores 0.333 and does not). Every WS-7 echo golden test passes
unchanged. `theme_signature`'s old name is gone, so no future caller can pick the wrong one by accident.

**Why D2 before D7.** Expanding a curated list buys most of the coverage while keeping the closed-vocabulary
echo guarantee, so it needs no privacy review, no DPIA question, and no new artifact. The open-vocabulary
variant is the only option that reopens all of that, and section 1.3's measurement suggests it may not be
needed. Reach for it last.

**Constraint.** Any vocabulary expansion stays in reviewed code or reviewed data. A runtime-learned or
auto-mined tag list would break the "echo-safe by construction" property that section 1.1 exists to protect.

### P2: Catalog integrity (finding 3.2)

| ID | Deliverable | Effort |
| --- | --- | --- |
| D8 | CI audit computing pairwise `structural_distance` across every production-eligible skeleton in each cell, failing below `TAU_CELL` (0.05). Applies the anti-clone floor to the whole catalog, not just to mutation-derived promotion candidates. | S |
| D9 | Resolve the live clone pair: `the-sunken-temple` and `the-harrowstone-keep` are the same 550-node tree in the same 13-16/long/gamebook cell at distance 0.00095. Retire one, mutate one past the floor via the WS-5 operators, or re-cell it. Whichever is chosen, the cell must end with 5 genuinely distinct trees, not 4 and a duplicate. | M |
| D10 | Either extend `structure_fingerprint` to canonicalise node ids by graph position, or document it as an identity check that is explicitly **not** a clone check and route clone questions to `structural_distance`. Today it reports the clone pair as different because their node ids differ, so every equality-based check built on it is blind to renamed clones. | S |

**Acceptance.** D8 fails on the current `main` before D9 and passes after. `13-16/medium/gamebook`, minimum
in-cell distance 0.091, is reviewed as a near-miss even though it clears the floor.

### P3: Make escalation actually act (findings 3.3, 3.7, 3.8)

| ID | Deliverable | Effort |
| --- | --- | --- |
| D11 | Thread `DifferentiationLevel` and the top-k neighbours into `fill_skeleton`, and add a conditional escalated block to `fill.md`: an avoid-list plus a directive to vary tone, cast relationships, and pacing rather than surface nouns. **Privacy constraint: pass the prior fills' published titles, settings, and cast, which are generated content the family already has, never the prior requests' premises.** That keeps one family member's request text out of another's generation prompt and satisfies constraint 4. Fence at reuse per safety invariant 4. | M |
| D12 | A variation-axis library: an authored set of axes (narrative distance, tonal register, sensory emphasis, pacing, whose point of view the scene favours) with one drawn per request and passed to the fill. Varies the *dimension* of variation rather than sampling noise, so it does not trade against the reading-level stability the WS-0 lexical guards watch. | S |
| D13 | Feature-vector-aware selection weighting: de-weight a candidate by `structural_distance` and `valence_hist` proximity to the reader's recent stories, not by slug identity alone. `structure_features` already computes everything needed. Keeps the `1/(1 + ...)` novelty floor. | M |

**Acceptance.** ATG masked distance between two fills of one tree at `LEAF` escalation beats the same pair at
`TREE` escalation by a measurable margin on the WS-0 panel. D13 makes the section 3.2 clone pair
self-correcting: the second of two near-identical trees is de-weighted like the repeat it is, independent of
D9.

### P4: Fail-path depth and outcome mix (section 1.2)

The phase the second review challenge produced, then substantially narrowed. **D14 is the primary
deliverable and it is small.** It extends PL-20's existing, ratified depth principle from the winning path to
every path, which is what PL-20's docstring declares out of scope. D16 measures what readers actually
receive; D15 and D18 are the product decisions PL-20's authors deliberately left open.

| ID | Deliverable | Effort |
| --- | --- | --- |
| D14 | **PL-22, a fail-depth floor, scoped to foreclosing terminals.** No `death`/`capture` ending may sit closer to `start_node` than a set fraction of the cell's `min_complete`. Scoped per section 1.12: a `setback` terminal auto-loops to a safe point at negligible cost, so only a foreclosing terminal leaves the reader with a restart decision. That narrows the affected set from 178 endings to **73**, and no skeleton then falls below its `min_endings` floor. Same enforcement shape as PL-20 (BFS from `start_node`), same `band_profile.py` cell table. | S |
| D15 | Ratify PL-22's fraction as an ADR-011 amendment. 25% and 33% are both defensible; 50% is a genuine rebalance (395 endings, 22.2%) and should be rejected unless D16's data demands it. The amendment should state the principle explicitly: the age-appropriate-depth guarantee applies to every path a reader can take, not only to the winning one. | S |
| D16 | Instrument **real** reading depth. `ReadingState` and `Completion` already hold what is needed: nodes visited per session, terminal reached, endings collected per profile, re-reads per storybook. Report the distribution of depth-reached against `min_complete` per cell, the share of sessions terminating below PL-22's candidate fractions, and the **real satisfying-ending rate** per book and per profile (the calibration input D18's SPM floor needs). This replaces the structural proxies (choice-uniform walk and BFS ending depth) with measurement, and it is what decides whether D17 is needed at all. | M |
| D17 | Remediate the foreclosing endings PL-22 rejects, via WS-5's M2 ending re-map: relocate the terminal deeper rather than deleting it. At 33% that is **73** `death`/`capture` endings across 7 skeletons, concentrated in `the-tenfold-siege` (23), `the-serpent-vaults` (12), `the-labyrinth-of-glass` (11), and `the-pale-road` (12). Ending-count-preserving relocation is no longer forced by the floor (section 1.12) but remains the better default. Every remutated tree re-runs the full gate. | M |
| D18 | **A satisfying-path-mass (SPM) floor keyed on topology**, replacing the `min_positive_endings` count this deliverable previously proposed (section 1.9: count and mass are decoupled, and `the-drowned-court` has 5 positive endings at 0.00% SPM). Floor the share of playthroughs reaching a `success`/`completion` ending, keyed on `structure_features().topology` so a `gauntlet` earns a lower floor than a `sorting_hat`. Explicitly permit reconvergence and high top-k concentration; leave positive ending count unconstrained. Calibrate against D16 telemetry, not the model alone. | M |
| D19 | **Accepted** (section 1.7): require in-cell **outcome spread** so candidates in one cell occupy different points in the valence envelope. A cell holding one 95% gauntlet, one ~80% harsh-but-survivable, and one ~60% tense-but-fair is still entirely gamebook, and it varies how the cell *plays* rather than only how it reads. Enforced by the D5 audit. Hold until D16 shows whether readers experience the uniformity. | M |

**Acceptance.** PL-22 fails on the current `main` for the 100 endings below a 25% floor and passes after D17.
D16 publishes the measured depth-reached distribution per cell. No skeleton regresses on PL-20: converting a
terminal to a routing `setback` must not shorten any winning path.

**Framing note.** This phase does not make gamebooks easy, and it does not touch the 98% ratio. ADR-011 chose
"few wins + many fails" and that stays; median ending depth is already 16 to 43 nodes, so the books are
substantial. The gap is a shallow tail that PL-20 deliberately does not cover, and the reason to close it is
that a reader who exits at node 2 has read only the shared opening funnel, which is where perceived sameness
between two structurally distinct books is manufactured. One rule, one constant per cell, and about a hundred
ending re-maps.

### P5: Per-reader scoping and guard hardening (findings 3.5, 3.6)

| ID | Deliverable | Effort |
| --- | --- | --- |
| D20 | Optional `profile_id` scoping in `load_family_history` and `recent_skeleton_usage`. Prefer per-profile history for weighting and for the ATG partner, falling back to family scope when a profile is too new. Perceived similarity is a per-reader phenomenon; today a 20-row window is shared across all a family's children, and a sibling's fill can be the ATG comparison partner. | M |
| D21 | ATG against the k most recent same-tree fills (or the k nearest by similarity signature), taking the minimum distance as the verdict input, so templating that recurs with a gap stops being invisible. Then calibrate the empty per-band threshold table and decide the promotion from advisory to blocking, which WS-1 already tracks as open. | M |
| D22 | Consider counting distinct storybooks rather than versions in the recency window, or raise the 20-row cap. Retries and re-authored versions currently consume window slots, so a family that re-authors heavily has a much shorter effective memory. `skeleton_match` documents the version-counting choice as deliberate; this is a product decision to revisit, not a bug to fix. | S |

### P6: Raise the ceiling (findings 3.4, 2.1)

| ID | Deliverable | Effort |
| --- | --- | --- |
| D23 | **Alternate beat phrasings.** Author two or three interchangeable beat variants per node sharing one *outcome contract* (same successor state, same choice semantics, same role and word target) but delivering it through a different scene. Selection draws a variant set per fill; the Stage 1 fidelity gate checks the fill against whichever variant was issued, so it keeps working unchanged. Needs a design doc and probably an ADR. | L |
| D24 | Grow the small cells. Fourteen of eighteen cells hold exactly three trees, which is the root arithmetic constraint: a child reading four stories at one band and length must see a tree twice. WS-8's flywheel owns the automated path; this is the reminder that three-per-cell is the number to beat, and that D5 must gate every addition. | L |

**Why D23 is the ceiling.** `beats=` is byte-identical across every fill of a skeleton, forever, and `fill.md`
requires the prose to depict that exact beat with the Stage 1 gate enforcing it. So every fill of
`the-cave-of-echoes` contains a two-way split where one branch looks inviting and one looks like a warning, at
the same depth, with the same word budget. Pushing `fill.md` harder collides with the fidelity gate, and
fidelity wins because it is the blocking one. D23 is the only deliverable that lifts that cap: it makes
`beats` a contract the pipeline checks rather than a string it freezes.

### P7: Visibility authorization and tiered privacy controls (section 1.4)

The owner's two-prong proposal, with the authorization rule specified in section 1.5. D25 is the blocker:
without an intake-time guardian ceiling, nothing else in this phase can be conditioned on anything.
Independent of P1 through P6 and it does not gate them: P1's expansion path needs no visibility tiering at
all, since a curated closed vocabulary is already safe on both prongs.

| ID | Deliverable | Effort |
| --- | --- | --- |
| D25 | **Guardian visibility ceiling at intake.** A guardian-set field on the story request, so the pipeline can branch at request and fill time and so the admin has something to be bound by. Today `Visibility` is chosen by the admin at release approval, at the end of the pipeline, long after the signature is derived and the echo is rendered. Set from the authenticated principal's acting role, never from a client-supplied role: `initiator_role` is already derived this way (`story_requests/service.py`, marked `#CRITICAL: security`) and the ceiling must follow the same pattern so a child cannot set it. | S |
| D26 | **`resolve_visibility`, a pure lattice meet.** Implement section 1.5's rule as a pure function plus a frozen table, mirroring `state_machine.LEGAL_TRANSITIONS`, and enforce it in `publishing`'s approve service rather than only in the API layer. Unit-testable with no database, exactly like `LEGAL_TRANSITIONS`. | S |
| D27 | **Fix the `ApproveBody` default, which becomes a silent downgrade.** `ApproveBody.visibility` defaults to `"family"` today, which is safe when the admin is the only decider. Under the ceiling rule an omitted body would silently restrict a guardian's `catalog` book to family. Change the semantics: an omitted body means "honor the guardian ceiling", not "family". This is a wire-contract change and needs the OpenAPI client regenerated. | S |
| D28 | **Audit every resolution.** Record `(guardian_ceiling, admin_choice, resolved, actor, initiator_role)` in the pipeline event log on each approve. Visibility is a disclosure decision, so "why is this book family-only" must be answerable after the fact, and a rule that silently lowers a setting is exactly the kind of thing that needs a trail. | S |
| D29 | **Catalog path: decouple rather than scrub.** On a catalog-visibility book, do not publish the family-facing WS-7 interpretation or echo cross-family at all; the catalog listing carries only skeleton-derived and generated metadata (title, cover, themes, band, length). A structural guarantee, not a redaction filter that has to be right every time. | M |
| D30 | Family-only relaxation, scoped honestly. Document exactly what the relaxation covers (intra-family echo of the family's own request) and what it does **not** (LLM-provider export, which visibility does not gate, and which still sits behind `privacy-model.md`'s open OpenRouter retention blocker). Any relaxation whose stated basis is "the data never leaves the family" is mis-scoped. | S |
| D31 | Gate the catalog prong on Phase 7 compliance. ADR-016 makes the catalog the widest ring of the three-ring boundary, and `privacy-model.md`'s "If Shared Beyond Family" section lists COPPA and Kids Category compliance as an unfinished Phase 7 launch blocker. Routing child-premise-derived books cross-family should wait on that work regardless of what the flag permits. | S |
| D32 | **Guardian ceiling-change path** (section 1.6): a guardian-surface action to raise or lower their own ceiling, audited through D28's trail, with copy stating what becomes visible to other families. No content re-screen is required, and the reason is recorded in section 1.6 so a future reader does not add one as a precaution. Post-publish changes route through an explicit human-invoked path, never a bare column update. | M |
| D33 | **Assert D29's exclusion is read-time, not publish-time.** A test that widens a published family-only book to catalog and asserts the cross-family read surface still exposes no family-facing interpretation or echo. This is the load-bearing requirement behind allowing ceiling changes at all; if the filter is applied when serving, widening is safe by construction. | S |
| D34 | **Evaluate `resolve_visibility` against the acting role**, using the existing `principal.acting_role(family_id)` rather than identity or the `is_admin` capability. Test that a dual-role adult acting as admin cannot raise their own family's guardian ceiling, and that the same person acting as guardian can. | S |
| D35 | Restore or repoint `coppa-gdpr-remediation-plan.md`, cited by `story_requests/interpretation.py` as governing Route A self-naming policy but absent from `docs/planning/`. | S |

**Acceptance.** A story request carries a guardian ceiling from intake. `resolve_visibility` rejects every
loosening transition in section 1.5's table, enforced in the service layer and covered by unit tests with no
database. An approve with no body on a guardian-`catalog` book resolves to `catalog`, not `family`. A
catalog-visibility book exposes no premise-derived free text cross-family, verified by a test asserting the
interpretation and echo fields are absent from the cross-family read surface.

**Note on ordering.** If P1 lands as D2 plus D3 (expanded curated vocabulary, containment measure), the
privacy question that motivated the tiering largely evaporates: a closed reviewed vocabulary is echo-safe on
both prongs, so no relaxation is needed to get the diversity benefit. P7 then stands on its own product merits
(guardians wanting to share good books, and the authorization rule being correct) rather than as a privacy
workaround. That is the better outcome, and a reason to do P1 first.

### P8: Pre-submission expectation setting (section 1.8)

The pre-submission half of [K19](capability-register.md), complementing WS-7's post-submission reflection.
Independent of every other phase. Small, and it addresses the most direct cause of a child feeling the book
"did not turn out as expected": three of the six requester-facing restrictions can never be explained after
the fact, because `_ELEMENT_MUST_BE_NULL` forbids echoing the offending phrase.

| ID | Deliverable | Effort |
| --- | --- | --- |
| D36 | **Serve the restriction set from the API**, keyed on the requesting profile's band, derived from `ReasonCode`, `band_profile`, and the profile's `content_nogo` rather than hand-written copy. A hard-coded list on the page drifts from enforcement the first time any of those changes, and a stated restriction that no longer matches behaviour is worse than none. | M |
| D37 | **Surface it on the kid request surface** (`frontend/src/library/RequestStory.tsx`), which today shows one prompt, a 500-character textarea, and no restrictions at all. Positive, band-appropriate framing: the hero gets a made-up name, no real names or contact details, the story's shape is already set. | M |
| D38 | **Surface the fuller set on the guardian intake surface** (`frontend/src/guardian/IntakePage.tsx`), including the family's actual `content_nogo` list, which the guardian set and can change. | S |
| D39 | **Enforce the resolved `GUARDIAN_CONTROL` disclosure level** (section 1.8, owner-decided): the kid surface states only that some themes are off. D36's kid-surface response must omit the `content_nogo` values entirely rather than sending them for the client to hide, and the copy must be invariant to the list's contents so it cannot leak membership by changing. Test both. | S |
| D40 | Regression-test the pair: a request naming the requesting child resolves to `IDENTITY_PROTECTION`, and the restriction the API served for that band covers it. Keeps the stated restrictions and the enforced ones from diverging silently, which is the failure mode D36 exists to prevent. | S |

### P9: Series continuity (section 1.10)

Two validator gaps the owner's single-start-point rule exposed, plus the remediation of the one series in the
catalog. Small, and it shares its remediation pass with D17.

| ID | Deliverable | Effort |
| --- | --- | --- |
| D41 | **Retracted, see section 1.12.** SR-8 (forbidding continuation-foreclosing ending kinds in a non-final series book) is unnecessary once restart-on-fail exists: a foreclosing terminal forecloses the *attempt*, not the series, and SR-5 already requires a reachable satisfying ending. Kept as a numbered entry so the reasoning is not rediscovered. **Depends on P10 shipping**; if restart-on-fail is deferred, SR-8 comes back. | none |
| D42 | **Resolved (section 1.12): neither `death` nor `capture` forecloses continuation**, given restart. Both foreclose an attempt. No kind set to fix. | none |
| D43 | **SR-9: the highest-index book must be `is_final`, or a successor must exist.** SR-4 flags a book below the highest index that *is* final; SR-5 skips the highest index entirely, so a chain can promise a continuation that does not exist. `brass-lantern` book 2 declares `is_final: false` with no book 3 and passes both rules today. | S |
| D44 | **`brass-lantern` needs no continuity remediation** (section 1.12): its 94 `death`/`capture` endings per book are fine once restart exists, and all 12 of each book's shallow terminals are `setback`, so PL-22 asks nothing of it either. What it still needs is the D9 structural-clone resolution, which is already tracked there. | none |
| D45 | Record the series-plus-gamebook tension in ADR-011's amendment: a series book's fails must be `setback`-shaped rather than lethal, so the combination is more constrained than either style alone. `brass-lantern` reads as authored gamebook-first and series-second, which is how it acquired 94 foreclosing endings. | S |

### P10: Implement `restart-on-fail` (section 1.11)

The root-cause phase. ADR-011 specifies the primitive, the schema cannot express it, and the checkpoint
mechanism is built with no producer. Highest leverage in the whole plan for the gamebook cells, because it
addresses the cause rather than the symptoms P4 measures. Needs an ADR amendment and a design doc before code.

| ID | Deliverable | Effort |
| --- | --- | --- |
| D46 | **Engine-written checkpoints at derived safe points** (section 1.12, resolved). A safe point is the most recent visited non-ending node with more than one visible choice and at least one choice untaken, computed from the persisted `path`/`var_state`/`visit_set`. No new `EffectOp`, no authored marker, no bottleneck heuristic: the engine snapshots into `save_slots` as the reader passes one. Snapshots are mandatory rather than optional because `choice_path` is not persisted, so historical `var_state` cannot be re-derived when two choices share a target with different effects. | M |
| D47 | **Two-tier restart behaviour** (section 1.12). A `setback` terminal **auto-loops** the reader to the last safe point, restoring `var_state`, `visit_set`, and position from the snapshot, landing them where a different path is available. A foreclosing terminal instead **offers a choice**: restart from the last safe point, or restart from node 1. API plus reader UI over existing primitives. | M |
| D48 | **Checkpoint placement at or past the funnel-clearing depth** (section 1.11 consequence 2): a restart that returns the reader to node 1 re-reads the shared opening funnel, which is the diversity failure PL-22 exists to prevent. Reuse the same 33%-of-`min_complete` quantity from section 1.7 rather than deriving a second number. | S |
| D49 | **Amend ADR-011** to record that `restart-on-fail` is a player-level loop over hard terminals rather than a graph edge, since `Node` forbids choices on an ending node and that invariant is worth keeping. The ADR currently implies a graph edge ("negative ending -> start/checkpoint"), which is not implementable as written. | S |
| D50 | **Re-shape D18's floor as a session-level measure** once D47 ships: cumulative satisfying rate per session across restarts, with structural per-walk SPM retained as the design gate. Without this, D18 would floor a metric that restart-on-fail deliberately makes unrepresentative. | S |
| D51 | Audit whether `save_slots` should stay unwritable until D46 lands. It is currently correct plumbing with no producer, which is harmless but invites a future contributor to assume checkpoints work. Either document it as reserved-for-D47 or gate it behind the same decision. | S |
| D52 | **Per-(profile, series) mode row.** The one schema addition challenge mode needs: nothing currently holds per-profile series state, since progress is implicit in per-book `ReadingState` plus `Completion` rows. Carries the mode flag and gives series progress a home it currently lacks. Band-gated to 13-16 and 16+ per section 1.13. | M |
| D53 | **Series-reset operation:** atomic, server-authoritative, resetting every `ReadingState` row for the profile across the series' books while **preserving `Completion` rows**, and correct against `state_revision` on every affected row. Never applied optimistically on-device: a death arriving through `offline/sync.ts` must not destroy a run during conflict resolution. | M |
| D54 | **Opt-in surface with the consequence stated up front** ("if your character dies, you start again at the very beginning of book 1"), guardian-visible, at the point of enabling rather than on first death. Section 1.8's principle on a new surface. | S |
| D55 | **Mode-change policy:** allow a downgrade from challenge to normal at any time, but never retroactively undo a death that has already reset the run. Preserves the challenge without trapping a child in an experience they no longer want. | S |
| D56 | Decide whether a guardian may withdraw challenge-mode availability for a profile. A product decision rather than a safety one, since the mode cannot expose content the band forbids. | S |

---

## 4. Sequencing

```text
P1 (similarity signal)  -----+
   D1 -> D2, D3 -> D4, D5, D6  |   (D7 = open-vocab fallback, only if needed)
                            +--> P3 (escalation acts: D11, D12, D13)
P2 (catalog integrity)  ----+         |
   D8 -> D9, D10                       +--> P5 (per-reader, guard hardening: D20, D21, D22)
                                      |
P4 (fail-path depth + outcome mix) ----+
   D14 -> D15 -> D17      (PL-22: rule, ratify, remediate)
   D16 (measure)  ->  D18, D19 gated on it

P6 (ceiling: D23, D24)   independent, longest lead time, start the D23 design early
P7 (visibility: D25 -> D26, D27, D28 -> D29..D32, D34)   independent; D25 unblocks the rest
     D33 (read-time filter test) gates D32
P8 (expectation setting: D36 -> D37, D38, D39, D40)   independent; no open decisions
P9 (series: D42 -> D41, D43; D44 shares D17's remediation pass; D45)
P10 (restart-on-fail: D46 -> D47 -> D48, D50; D49, D51)   root cause; ADR-011 amendment first
     challenge mode: D52 -> D53 -> D54, D55; D56   opt-in, 13-16 and 16+ only
```

P1 before P3: escalation cannot act on a signal that does not fire. P1 before any metric claim: until the
similarity signal covers real requests and the catalog is clone-free, the WS-0 dashboard reports on a system
whose diversity machinery is mostly inert, and its numbers will look better than the reader's experience.
D14 does not wait on D16: PL-22 at 25% of `min_complete` is justified by the structural asymmetry alone (a
terminal at node 2 against a 29-node win floor), and D16's telemetry then tells us whether to tighten toward
33%. D16 does gate D18 and D19, which are product decisions that should not be made on a proxy. D23's design
can start immediately since it blocks on nothing here.

Suggested first slice, roughly one sprint: D1-D6 (the whole vocabulary and measure fix), D8 and D10
(catalog audit and the fingerprint clarification), D12 (variation axes), D14 (PL-22), plus starting
D16's instrumentation.
That turns the signal on safely, gates the catalog, closes the shallow-terminal tail, adds the cheapest real
leaf-diversity gain, and begins collecting the depth data the rest of P4 needs.

---

## 5. Metrics added

Beyond the WS-0 suite:

| Metric | Definition | Serves |
| --- | --- | --- |
| Similarity-signature coverage | Share of real requests yielding a non-empty signature | D2 |
| Escalation trigger rate | Share of requests recommending `LEAF` or `CATALOG` | D2, D3 |
| In-cell minimum structural distance | Per cell, lowest pairwise `structural_distance` | D8, D9 |
| Shallow-terminal share | Per skeleton, endings whose BFS depth is under 25%/33% of the cell's `min_complete` | D14, D17 |
| Depth-reached distribution | Real nodes visited per session before a terminal, as a ratio of `min_complete` | D16 |
| Early-exit rate | Share of real sessions terminating below PL-22's candidate fractions | D14, D16 |
| Satisfying path mass (SPM) | Share of choice-uniform playthroughs reaching a `success`/`completion` ending; the structural design gate | D18 |
| Ending-mass concentration | Share of terminal mass on the top-k endings, and how many declared endings are ever reached | D18 |
| Satisfying-ending rate | Real share of readers reaching a `success`/`completion` ending per storybook; the SPM floor's calibration input | D16, D18 |
| Session satisfying rate | Cumulative share of reading *sessions* reaching a `success`/`completion` ending across restarts; supersedes per-walk SPM as the floor once D47 ships | D50 |
| Challenge-mode adoption and survival | Share of eligible profiles enabling it, and runs reaching book N before a series reset; tells us whether the mode is tuned or punishing | D52, D54 |
| Series continuation admissibility | Non-final series books with zero continuation-foreclosing endings | D41, D44 |
| Outcome-mix spread | Per cell, spread of negative-ending share across candidates | D19 |
| Escalated ATG lift | ATG masked distance at `LEAF` escalation minus the same pair at `TREE` | D11 |

The first two are the honesty check on this whole plan. If coverage stays low, nothing else in P3 or P5 is
doing anything, however good the code looks.

---

## 6. Decisions and open questions

### 6.1 Resolved

| Question | Decision | Where |
| --- | --- | --- |
| PL-22's fraction | **33% of `min_complete`.** 25% clears the rule's own funnel rationale on only 3 of 14 gamebook skeletons; 33% clears it on 13 of 14, at the same single ending-floor exception. Remediation must be ending-count-preserving. | 1.7, ratified by D15 |
| Is a ~60% tense-but-fair gamebook tree acceptable? | **Yes.** Legitimate in-cell variety; `narrative_style` promises the gamebook form, not a lethality rate. D19 becomes a design target. | 1.7 |
| May a guardian change their visibility ceiling later? | **Yes**, and it needs no content re-screen, because every content screen is already visibility-independent. | 1.6, built by D32 |
| Dual-role adults | Enforce the lattice on **the role being acted in**, via `principal.acting_role(family_id)`. | 1.6, built by D34 |
| Admin visibility lever | **Guardian sets a ceiling; the admin may only restrict.** `resolved = min(guardian_ceiling, admin_choice)`. | 1.5, built by D26 |
| What does the kid surface say about `GUARDIAN_CONTROL`? | **Only that some themes are off**, never the list. The kid-surface API response omits `content_nogo` entirely, and the copy stays invariant to the list's contents. | 1.8, built by D39 |
| How many winning arcs should a gamebook have? | **Wrong question: it is path mass, not ending count.** Floor the satisfying path mass, keyed on topology ("a reflection of the branching strategy"); leave positive ending count unconstrained; permit reconvergence. Ten positive endings at 0% mass must fail. | 1.9, built by D18 |
| Should gamebook fails be terminal? | **No: many paths should be setbacks, not end-of-story.** ADR-011 already specifies `restart-on-fail`; the schema forbids the edge and the checkpoint mechanism has no producer. Root cause of the P4 symptoms. | 1.11, built by P10 |
| Series end points | **Every ending must allow the next book's single start point**, satisfied by restart-on-fail rather than by restricting ending kinds. SR-8 retracted; `brass-lantern` needs no continuity remediation. | 1.10, 1.12 |
| Restart behaviour | **Two tiers.** A `setback` auto-loops to the last safe point; a foreclosing terminal offers last-safe-point or node 1. Safe point = most recent visited multi-choice node with an untaken choice, derived from persisted state. | 1.12, built by D46/D47 |
| Opt-in challenge mode | **Yes: a `death` resets the series to book 1, node 1, opt-in and never default.** Offerable at 13-16 and 16+ only, gated by existing policy (`death` is forbidden below 10-13; ADR-011 makes lethal restart-on-fail "13-16 up"). | 1.13, built by D52-D56 |
| What does "restart from node 1" mean in a state-carrying series? | **Two distinct resets.** Book-local node-1 restart preserves state inherited from book N-1; the series reset (book 1, node 1) discards it and is the challenge-mode consequence of `death`, not a casual menu item. | 1.13 |
| Does `capture` foreclose continuation? | **No, and neither does `death`**, given restart. Both foreclose an attempt. | 1.12 |
| Open vs curated vocabulary | **Expand the curated closed list**; the open-vocabulary variant drops to a fallback (D7) that may never be needed. | 1.3 |

### 6.2 Still open

- **Does the similarity signature need a DPIA addendum?** Only relevant if D7 is ever built. The design adds no
  personal data at rest and no new export, which is the basis for arguing no. A DPO or legal call, not an
  engineering one. D7 raises it; it does not answer it.
- **May a guardian withdraw challenge-mode availability for a profile?** D56. A product decision rather than a
  safety one, since the mode cannot expose content the band forbids. **The last open product decision in this
  plan.**
- **Should PL-22 become `max(0.33 * min_complete, funnel_clearing_depth)`?** One skeleton
  (`the-smugglers-cut`) has a funnel deeper than its 33% floor. Start with the constant plus a per-cell
  override; revisit on D16's telemetry.
- **Should the ATG become blocking, and at what per-band threshold?** Inherited from WS-1, unblocked by D21's
  calibration.
- **ADR candidate for D23.** Alternate beat phrasings move a safety-adjacent artifact from frozen string to
  checked contract. That deserves its own ADR alongside ADR-019 (parameterised skeletons) and ADR-020
  (mutation-derived catalog growth).

---

## 7. What is working, and must survive this plan

Repeated from the audit because a remediation plan is where hard-won properties get traded away by accident:

- **Deliberate topology variety per cell.** Every kid-band cell holds three distinct topologies at structural
  distance 0.20 to 0.49. D8 exists to protect this as automation grows the catalog.
- **Safety orthogonal to diversity.** Freezing the ADR-011 constraint grammar rather than the graphs is why
  every lever here is available without touching the gate.
- **The novelty floor.** No eligible tree is ever fully excluded. D13 and D20 keep the form.
- **Fail-closed binding.** `generation/binding.py` raises rather than falling back to `default_binding`. A
  silent fallback would ship the shipped default story, the most visible possible repeat.
- **The echo-safe guarantee.** The property section 1.1 nearly cost us. After D1 it is a named function with a
  documented reason to stay closed, which is stronger than the incidental protection it had before.
