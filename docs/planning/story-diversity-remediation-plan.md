---
schema_type: planning
title: "Story Diversity Remediation and Enhancement Plan"
description: "Phased plan to close the nine gaps in story-diversity-analysis.md and raise book diversity
  further. Records two corrections to that audit: the open-vocabulary theme signature is unsafe as drafted
  because the closed vocabulary is load-bearing for the WS-7 echo surface, and the gamebook cells' 98%
  negative ending share is ADR-011-intended with PL-20 working as designed, the real gap being a shallow
  fail-path tail that PL-20 explicitly leaves out of scope."
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
source: "story-diversity-analysis.md; review challenge on GDPR exposure of an open-vocabulary theme
  signature and on the 98% negative ending share in the gamebook cells; follow-up read of
  generation/worker.py::_degraded_set_aside_decisions, validator/band_profile.py, ADR-011 sections 6 and 8,
  privacy-model.md, player/engine.py, api/reading.py, validator/policy.py::_check_min_to_complete (PL-20);
  BFS win-path and fail-path depth measurement over the 14 production-eligible gamebook skeletons
  (2026-07-25)."
---

> **Companion documents.** [story-flexibility-plan.md](story-flexibility-plan.md) is the strategy of record.
> [story-diversity-analysis.md](story-diversity-analysis.md) is the current-state audit this plan executes.
> Finding references below (3.1, 3.2, ...) point at that audit's section numbers.

---

## 1. Two corrections to the audit

Both came out of review challenge, and both change the work. They are recorded here rather than silently
patched into the audit, because each rests on a fact the audit did not establish.

### 1.1 The open-vocabulary theme signature is unsafe as drafted

The audit's top recommendation was to replace `theme_signature`'s closed 12-tag vocabulary with an
open-vocabulary content-token signature. **As drafted that is a privacy regression, not just a diversity
fix.** The closed vocabulary is load-bearing for a surface the audit did not trace.

`generation/worker.py::_degraded_set_aside_decisions` turns each returned tag into a
`RawElement(phrase=tag)`, feeds it to `derive_dispositions`, and renders it through
`render_interpretation` into the WS-7 request interpretation: a kid-facing echo plus a guardian caption,
persisted on the story request. The code says so explicitly, twice:

```
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
|---|---|---|
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

```
PL-20: the shortest satisfying-completion path must meet the arc floor.
The shortest path in nodes from start_node to any success/completion ending must be at
least that floor; a too-short winning path (a hollow quick win) blocks.
Fail-fast negative endings are unaffected.
```

Measured against every production-eligible gamebook skeleton, it passes with margin everywhere. Shortest
winning path versus the cell floor, plus the depth distribution of negative endings (BFS node depth from
`start_node`, conditions ignored):

| Skeleton | Floor | Shortest win | Shortest fail | p10 fail | Median fail | PL-20 |
|---|---|---|---|---|---|---|
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
simply unmeasured, which is what D13 exists to fix.

**The narrow, real gap is the one PL-20 declares out of scope: "Fail-fast negative endings are unaffected."**
The depth principle is enforced on the winning path and has no sibling rule on the fail path, so a tree can
satisfy a 29-node win floor while offering a terminal at node 2. Shortest fail runs at **7% to 17% of the win
floor**, and `the-sunspire-ascent` and `the-drowned-court` both terminate as early as node 2.

Sizing the remediation across all 1,778 endings in the 14 gamebook skeletons:

| Fail-depth floor | Endings below it | Share |
|---|---|---|
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
rule. That remains a product decision for D11 to ratify, now independent of the depth question.

Note also that re-reading is a supported loop: `api/reading.py::list_completions` tracks "every ending a child
profile has completed" per profile, so ending-collection is expected. That is an argument for closing the
shallow tail rather than against it: every re-read that exits early re-reads the same opening funnel.

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
   D1-D4 and D8.
5. The WS-7 echo path is byte-identical after D1. A privacy-motivated refactor that changes what a child sees
   has failed.

---

## 3. Phases and deliverables

Six phases. P1 and P2 are prerequisites for trusting any diversity metric and should land first. Effort is
S (under a day), M (a few days), L (a sprint or more).

### P1: Unblock the similarity signal, privacy-safely (finding 3.1)

Nothing downstream of similarity works until this lands. Sequenced so the privacy split precedes the coverage
change, never the reverse.

| ID | Deliverable | Effort |
|---|---|---|
| D1 | Split `theme_signature` into `echo_signature` (today's closed-vocabulary function, renamed, behaviour byte-identical) and a new `similarity_signature`. Repoint `worker.py`'s two degraded-interpretation call sites at `echo_signature`; repoint `history.py` and `query.py` at `similarity_signature`. Pure refactor: `similarity_signature` initially delegates to the closed map so this commit changes no output. | S |
| D2 | Implement `similarity_signature` as open-vocabulary: `content_tokens(mask_tokens(premise, extract_entities(...)))`, retaining `_THEME_TAG_MAP` as a synonym-collapsing layer on top so "dragon"/"wyvern" still merge. Cap the token set for stability. Never rendered, never persisted, never prompted. | M |
| D3 | Make "unknown" distinct from "dissimilar". `jaccard_similarity(frozenset(), frozenset())` currently returns `0.0`, so an unrecognised theme is affirmatively scored as maximally dissimilar to a byte-identical prior request. Return an explicit unknown, and have `score_history` treat it **conservatively** (assume similar) so the failure mode is over-diversifying rather than silently disabling. | S |
| D4 | Add a `privacy-model.md` entry classifying the similarity signature as a transient, in-memory, non-persisted, non-exported derivation of already-held data, with an explicit "adds no new personal data at rest, so no new retention or erasure obligation" statement. Flag for DPO or legal review whether the DPIA needs an addendum under ADR-018. | S |

**Acceptance.** A panel of realistic premises (pets, sports, family, school, music, inventions, alongside the
12 existing tropes) yields a non-empty similarity signature for over 95%, and two paraphrases of one request
score above `tau_theme`. Every WS-7 echo golden test passes unchanged. A grep proves `similarity_signature`
has no call site in any render, persist, or prompt path. `theme_signature`'s old name is gone, so no future
caller can pick the wrong one by accident.

**Risk.** D2 changes the input distribution of `tau_theme` (0.35), which was tuned against a 12-tag space.
Open-vocabulary Jaccard runs lower for the same perceived similarity. D2 must re-derive `tau_theme` on the
same panel and record the new value with its basis, or the ladder will under-trigger for the opposite reason.

### P2: Catalog integrity (finding 3.2)

| ID | Deliverable | Effort |
|---|---|---|
| D5 | CI audit computing pairwise `structural_distance` across every production-eligible skeleton in each cell, failing below `TAU_CELL` (0.05). Applies the anti-clone floor to the whole catalog, not just to mutation-derived promotion candidates. | S |
| D6 | Resolve the live clone pair: `the-sunken-temple` and `the-harrowstone-keep` are the same 550-node tree in the same 13-16/long/gamebook cell at distance 0.00095. Retire one, mutate one past the floor via the WS-5 operators, or re-cell it. Whichever is chosen, the cell must end with 5 genuinely distinct trees, not 4 and a duplicate. | M |
| D7 | Either extend `structure_fingerprint` to canonicalise node ids by graph position, or document it as an identity check that is explicitly **not** a clone check and route clone questions to `structural_distance`. Today it reports the clone pair as different because their node ids differ, so every equality-based check built on it is blind to renamed clones. | S |

**Acceptance.** D5 fails on the current `main` before D6 and passes after. `13-16/medium/gamebook`, minimum
in-cell distance 0.091, is reviewed as a near-miss even though it clears the floor.

### P3: Make escalation actually act (findings 3.3, 3.7, 3.8)

| ID | Deliverable | Effort |
|---|---|---|
| D8 | Thread `DifferentiationLevel` and the top-k neighbours into `fill_skeleton`, and add a conditional escalated block to `fill.md`: an avoid-list plus a directive to vary tone, cast relationships, and pacing rather than surface nouns. **Privacy constraint: pass the prior fills' published titles, settings, and cast, which are generated content the family already has, never the prior requests' premises.** That keeps one family member's request text out of another's generation prompt and satisfies constraint 4. Fence at reuse per safety invariant 4. | M |
| D9 | A variation-axis library: an authored set of axes (narrative distance, tonal register, sensory emphasis, pacing, whose point of view the scene favours) with one drawn per request and passed to the fill. Varies the *dimension* of variation rather than sampling noise, so it does not trade against the reading-level stability the WS-0 lexical guards watch. | S |
| D10 | Feature-vector-aware selection weighting: de-weight a candidate by `structural_distance` and `valence_hist` proximity to the reader's recent stories, not by slug identity alone. `structure_features` already computes everything needed. Keeps the `1/(1 + ...)` novelty floor. | M |

**Acceptance.** ATG masked distance between two fills of one tree at `LEAF` escalation beats the same pair at
`TREE` escalation by a measurable margin on the WS-0 panel. D10 makes the section 3.2 clone pair
self-correcting: the second of two near-identical trees is de-weighted like the repeat it is, independent of
D6.

### P4: Fail-path depth and outcome mix (section 1.2)

The phase the second review challenge produced, then substantially narrowed. **D11 is the primary
deliverable and it is small.** It extends PL-20's existing, ratified depth principle from the winning path to
every path, which is what PL-20's docstring declares out of scope. D13 measures what readers actually
receive; D12 and D15 are the product decisions PL-20's authors deliberately left open.

| ID | Deliverable | Effort |
|---|---|---|
| D11 | **PL-22, a fail-depth floor.** The sibling rule PL-20 never had: no terminal ending may sit closer to `start_node` than a set fraction of the cell's `min_complete`. Measured sizing says a floor at 25% touches 100 of 1,778 gamebook endings (5.6%), and 33% touches 178 (10.0%). Same enforcement shape as PL-20 (BFS shortest path from `start_node`), same `band_profile.py` cell table, so it costs one rule and one constant per cell. | S |
| D12 | Ratify PL-22's fraction as an ADR-011 amendment. 25% and 33% are both defensible; 50% is a genuine rebalance (395 endings, 22.2%) and should be rejected unless D13's data demands it. The amendment should state the principle explicitly: the age-appropriate-depth guarantee applies to every path a reader can take, not only to the winning one. | S |
| D13 | Instrument **real** reading depth. `ReadingState` and `Completion` already hold what is needed: nodes visited per session, terminal reached, endings collected per profile, re-reads per storybook. Report the distribution of depth-reached against `min_complete` per cell, plus the share of sessions terminating below PL-22's candidate fractions. This replaces both proxies (random walk and BFS ending depth) with measurement, and it is what decides whether D14 is needed at all. | M |
| D14 | Remediate the endings PL-22 rejects, via WS-5's M2 ending re-map: convert an early lethal terminal into a `setback` that routes back into the graph rather than deleting it. At 25% that is 100 endings across 14 skeletons, concentrated in `the-ashfall-expedition` (19), `the-drowned-court` (15), `the-serpent-vaults` (11), and the clone pair (10 each). Every remutated tree re-runs the full gate. | M |
| D15 | Give "few wins" a number. 2 to 5 winning endings out of 74 to 209 is unconstrained by any rule; ADR-011 specifies terminal *fraction* but not valence mix. Add a `min_positive_endings` scaling with ending count, and optionally a negative-share ceiling. Independent of the depth work, and a product decision rather than a defect. | M |
| D16 | Optional, pending D13: require in-cell **outcome spread** so candidates in one cell occupy different points in the valence envelope. A cell holding one 95% gauntlet, one ~80% harsh-but-survivable, and one ~60% tense-but-fair is still entirely gamebook, and it varies how the cell *plays* rather than only how it reads. Enforced by the D5 audit. Hold until D13 shows whether readers experience the uniformity. | M |

**Acceptance.** PL-22 fails on the current `main` for the 100 endings below a 25% floor and passes after D14.
D13 publishes the measured depth-reached distribution per cell. No skeleton regresses on PL-20: converting a
terminal to a routing `setback` must not shorten any winning path.

**Framing note.** This phase does not make gamebooks easy, and it does not touch the 98% ratio. ADR-011 chose
"few wins + many fails" and that stays; median ending depth is already 16 to 43 nodes, so the books are
substantial. The gap is a shallow tail that PL-20 deliberately does not cover, and the reason to close it is
that a reader who exits at node 2 has read only the shared opening funnel, which is where perceived sameness
between two structurally distinct books is manufactured. One rule, one constant per cell, and about a hundred
ending re-maps.

### P5: Per-reader scoping and guard hardening (findings 3.5, 3.6)

| ID | Deliverable | Effort |
|---|---|---|
| D17 | Optional `profile_id` scoping in `load_family_history` and `recent_skeleton_usage`. Prefer per-profile history for weighting and for the ATG partner, falling back to family scope when a profile is too new. Perceived similarity is a per-reader phenomenon; today a 20-row window is shared across all a family's children, and a sibling's fill can be the ATG comparison partner. | M |
| D18 | ATG against the k most recent same-tree fills (or the k nearest by similarity signature), taking the minimum distance as the verdict input, so templating that recurs with a gap stops being invisible. Then calibrate the empty per-band threshold table and decide the promotion from advisory to blocking, which WS-1 already tracks as open. | M |
| D19 | Consider counting distinct storybooks rather than versions in the recency window, or raise the 20-row cap. Retries and re-authored versions currently consume window slots, so a family that re-authors heavily has a much shorter effective memory. `skeleton_match` documents the version-counting choice as deliberate; this is a product decision to revisit, not a bug to fix. | S |

### P6: Raise the ceiling (findings 3.4, 2.1)

| ID | Deliverable | Effort |
|---|---|---|
| D20 | **Alternate beat phrasings.** Author two or three interchangeable beat variants per node sharing one *outcome contract* (same successor state, same choice semantics, same role and word target) but delivering it through a different scene. Selection draws a variant set per fill; the Stage 1 fidelity gate checks the fill against whichever variant was issued, so it keeps working unchanged. Needs a design doc and probably an ADR. | L |
| D21 | Grow the small cells. Fourteen of eighteen cells hold exactly three trees, which is the root arithmetic constraint: a child reading four stories at one band and length must see a tree twice. WS-8's flywheel owns the automated path; this is the reminder that three-per-cell is the number to beat, and that D5 must gate every addition. | L |

**Why D20 is the ceiling.** `beats=` is byte-identical across every fill of a skeleton, forever, and `fill.md`
requires the prose to depict that exact beat with the Stage 1 gate enforcing it. So every fill of
`the-cave-of-echoes` contains a two-way split where one branch looks inviting and one looks like a warning, at
the same depth, with the same word budget. Pushing `fill.md` harder collides with the fidelity gate, and
fidelity wins because it is the blocking one. D20 is the only deliverable that lifts that cap: it makes
`beats` a contract the pipeline checks rather than a string it freezes.

---

## 4. Sequencing

```
P1 (privacy-safe signal)  ---+
   D1 -> D2 -> D3, D4       |
                            +--> P3 (escalation acts: D8, D9, D10)
P2 (catalog integrity)  ----+         |
   D5 -> D6, D7                       +--> P5 (per-reader, guard hardening: D17, D18, D19)
                                      |
P4 (fail-path depth + outcome mix) ----+
   D11 -> D12 -> D14      (PL-22: rule, ratify, remediate)
   D13 (measure)  ->  D15, D16 gated on it

P6 (ceiling: D20, D21)   independent, longest lead time, start the D20 design early
```

P1 before P3: escalation cannot act on a signal that does not fire. P1 before any metric claim: until the
similarity signal covers real requests and the catalog is clone-free, the WS-0 dashboard reports on a system
whose diversity machinery is mostly inert, and its numbers will look better than the reader's experience.
D11 does not wait on D13: PL-22 at 25% of `min_complete` is justified by the structural asymmetry alone (a
terminal at node 2 against a 29-node win floor), and D13's telemetry then tells us whether to tighten toward
33%. D13 does gate D15 and D16, which are product decisions that should not be made on a proxy. D20's design
can start immediately since it blocks on nothing here.

Suggested first slice, roughly one sprint: D1, D3, D4, D5, D7, D9, D11, plus starting D13's instrumentation.
That turns the signal on safely, gates the catalog, closes the shallow-terminal tail, adds the cheapest real
leaf-diversity gain, and begins collecting the depth data the rest of P4 needs.

---

## 5. Metrics added

Beyond the WS-0 suite:

| Metric | Definition | Serves |
|---|---|---|
| Similarity-signature coverage | Share of real requests yielding a non-empty signature | D2 |
| Escalation trigger rate | Share of requests recommending `LEAF` or `CATALOG` | D2, D3 |
| In-cell minimum structural distance | Per cell, lowest pairwise `structural_distance` | D5, D6 |
| Shallow-terminal share | Per skeleton, endings whose BFS depth is under 25%/33% of the cell's `min_complete` | D11, D14 |
| Depth-reached distribution | Real nodes visited per session before a terminal, as a ratio of `min_complete` | D13 |
| Early-exit rate | Share of real sessions terminating below PL-22's candidate fractions | D11, D13 |
| Satisfying-ending rate | Share of readers reaching a `success`/`completion` ending per storybook | D13, D15 |
| Outcome-mix spread | Per cell, spread of negative-ending share across candidates | D16 |
| Escalated ATG lift | ATG masked distance at `LEAF` escalation minus the same pair at `TREE` | D8 |

The first two are the honesty check on this whole plan. If coverage stays low, nothing else in P3 or P5 is
doing anything, however good the code looks.

---

## 6. Open questions

- **Does the similarity signature need a DPIA addendum?** The design adds no personal data at rest and no new
  export, which is the basis for arguing no. That is a DPO or legal call, not an engineering one. D4 raises it;
  it does not answer it.
- **What fraction of `min_complete` should PL-22 use?** 25% (100 endings) or 33% (178)? D12 ratifies it. The
  principle is not in question, only the number: PL-20 already establishes that depth is guaranteed, and PL-22
  extends that guarantee from the winning path to every path.
- **How many winning arcs should a gamebook have?** 2 out of 209 is unconstrained rather than chosen. D15 needs
  ratified numbers; ADR-011 specifies terminal fraction but not valence mix.
- **Does the D16 outcome-spread requirement conflict with `narrative_style` as a promise?** If a reader picks
  "gamebook" expecting a deadly maze, is a 60% tense-but-fair tree in that cell a broken promise or the
  variety the cell needs? Resolve before authoring against it.
- **Should the ATG become blocking, and at what per-band threshold?** Inherited from WS-1, unblocked by D18's
  calibration.
- **ADR candidate for D20.** Alternate beat phrasings move a safety-adjacent artifact from frozen string to
  checked contract. That deserves its own ADR alongside ADR-019 (parameterised skeletons) and ADR-020
  (mutation-derived catalog growth).

---

## 7. What is working, and must survive this plan

Repeated from the audit because a remediation plan is where hard-won properties get traded away by accident:

- **Deliberate topology variety per cell.** Every kid-band cell holds three distinct topologies at structural
  distance 0.20 to 0.49. D5 exists to protect this as automation grows the catalog.
- **Safety orthogonal to diversity.** Freezing the ADR-011 constraint grammar rather than the graphs is why
  every lever here is available without touching the gate.
- **The novelty floor.** No eligible tree is ever fully excluded. D10 and D17 keep the form.
- **Fail-closed binding.** `generation/binding.py` raises rather than falling back to `default_binding`. A
  silent fallback would ship the shipped default story, the most visible possible repeat.
- **The echo-safe guarantee.** The property section 1.1 nearly cost us. After D1 it is a named function with a
  documented reason to stay closed, which is stronger than the incidental protection it had before.
