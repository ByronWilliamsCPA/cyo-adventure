---
schema_type: planning
title: "Story Diversity Remediation and Enhancement Plan"
description: "Phased plan to close the nine gaps in story-diversity-analysis.md and raise book diversity
  further. Records four review corrections: the open-vocabulary theme signature is unsafe as drafted because
  the closed vocabulary is load-bearing for the WS-7 echo surface; the gamebook cells' 98% negative share is
  ADR-011-intended with PL-20 working as designed, the real gap being a shallow fail-path tail PL-20 leaves
  out of scope; expanding the curated vocabulary is the better fix and it exposes a symmetric-Jaccard defect
  that makes an identical premise score as dissimilar; the guardian family-only versus catalog two-prong is
  sound but blocked on visibility being set at approval rather than at intake; and visibility authorization is
  a monotone restriction rule where the guardian sets a ceiling the admin may lower but never raise."
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

Five items, each from a review challenge and each changing the work. They are recorded here rather than
silently patched into the audit, because each rests on a fact the audit did not establish. 1.1 and 1.2 correct
errors; 1.3, 1.4, and 1.5 are owner direction that reshapes the approach.

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
| D14 | **PL-22, a fail-depth floor.** The sibling rule PL-20 never had: no terminal ending may sit closer to `start_node` than a set fraction of the cell's `min_complete`. Measured sizing says a floor at 25% touches 100 of 1,778 gamebook endings (5.6%), and 33% touches 178 (10.0%). Same enforcement shape as PL-20 (BFS shortest path from `start_node`), same `band_profile.py` cell table, so it costs one rule and one constant per cell. | S |
| D15 | Ratify PL-22's fraction as an ADR-011 amendment. 25% and 33% are both defensible; 50% is a genuine rebalance (395 endings, 22.2%) and should be rejected unless D16's data demands it. The amendment should state the principle explicitly: the age-appropriate-depth guarantee applies to every path a reader can take, not only to the winning one. | S |
| D16 | Instrument **real** reading depth. `ReadingState` and `Completion` already hold what is needed: nodes visited per session, terminal reached, endings collected per profile, re-reads per storybook. Report the distribution of depth-reached against `min_complete` per cell, plus the share of sessions terminating below PL-22's candidate fractions. This replaces both proxies (random walk and BFS ending depth) with measurement, and it is what decides whether D17 is needed at all. | M |
| D17 | Remediate the endings PL-22 rejects, via WS-5's M2 ending re-map: convert an early lethal terminal into a `setback` that routes back into the graph rather than deleting it. At 25% that is 100 endings across 14 skeletons, concentrated in `the-ashfall-expedition` (19), `the-drowned-court` (15), `the-serpent-vaults` (11), and the clone pair (10 each). Every remutated tree re-runs the full gate. | M |
| D18 | Give "few wins" a number. 2 to 5 winning endings out of 74 to 209 is unconstrained by any rule; ADR-011 specifies terminal *fraction* but not valence mix. Add a `min_positive_endings` scaling with ending count, and optionally a negative-share ceiling. Independent of the depth work, and a product decision rather than a defect. | M |
| D19 | Optional, pending D16: require in-cell **outcome spread** so candidates in one cell occupy different points in the valence envelope. A cell holding one 95% gauntlet, one ~80% harsh-but-survivable, and one ~60% tense-but-fair is still entirely gamebook, and it varies how the cell *plays* rather than only how it reads. Enforced by the D5 audit. Hold until D16 shows whether readers experience the uniformity. | M |

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
P7 (visibility: D25 -> D26, D27, D28 -> D29, D30, D31)   independent; D25 unblocks the rest
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
| Satisfying-ending rate | Share of readers reaching a `success`/`completion` ending per storybook | D16, D18 |
| Outcome-mix spread | Per cell, spread of negative-ending share across candidates | D19 |
| Escalated ATG lift | ATG masked distance at `LEAF` escalation minus the same pair at `TREE` | D11 |

The first two are the honesty check on this whole plan. If coverage stays low, nothing else in P3 or P5 is
doing anything, however good the code looks.

---

## 6. Open questions

- **Does the similarity signature need a DPIA addendum?** The design adds no personal data at rest and no new
  export, which is the basis for arguing no. That is a DPO or legal call, not an engineering one. D7 raises it;
  it does not answer it.
- **What fraction of `min_complete` should PL-22 use?** 25% (100 endings) or 33% (178)? D15 ratifies it. The
  principle is not in question, only the number: PL-20 already establishes that depth is guaranteed, and PL-22
  extends that guarantee from the winning path to every path.
- **How many winning arcs should a gamebook have?** 2 out of 209 is unconstrained rather than chosen. D18 needs
  ratified numbers; ADR-011 specifies terminal fraction but not valence mix.
- **Does the D19 outcome-spread requirement conflict with `narrative_style` as a promise?** If a reader picks
  "gamebook" expecting a deadly maze, is a 60% tense-but-fair tree in that cell a broken promise or the
  variety the cell needs? Resolve before authoring against it.
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
