---
schema_type: planning
title: "Story Diversity Plan v2"
description: "Rebuilt diversity plan, grounded only in measurements that survived a seven-reviewer adversarial
  pass and a 98-document corpus survey. Twenty near-term deliverables, six independent defects, eight items deferred
  behind named prerequisites, five resolved owner decisions, a child-reader review folded in, a
  development-stage section re-ordering the work for a catalog with one author and one test household, and a
  reconciliation section against merged PR #418 (ADR-023) and open PR #416 that records personalization as a
  measured diversity lever. Replaces two superseded plans."
tags:
  - planning
  - generation
  - diversity
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give the diversity work a plan that stands on verified evidence. The previous two plans were
  superseded because their measurements held but much of the reasoning built on them did not; this rebuild
  separates the two explicitly and records what is deliberately NOT claimed."
component: Strategy
source: "story-diversity-analysis.md (measurements, as corrected); story-diversity-review-errata.md (the
  refutations and the corpus survey); runtime-semantics.md; validator-rules.md; pathfinder-structure-exploration.md;
  admin-guardian-dual-roles-plan.md; authorization-matrix.md; series-stress-test-findings.md;
  r1-deferred-debt-register.md; docs/compliance/coppa-gdpr-remediation-plan.md; PR #413. 2026-07-25.
  Reconciled 2026-07-26 against adr/adr-023-story-personalization-slots.md and capability-register.md v1.8
  (both merged in PR #418) and against open PR #416; see section 8."
---

> **Replaces** [story-diversity-remediation-plan.md](story-diversity-remediation-plan.md) and
> [story-diversity-execution-plan.md](story-diversity-execution-plan.md), both superseded.
> [story-diversity-analysis.md](story-diversity-analysis.md) remains the measurement record;
> [story-diversity-review-errata.md](story-diversity-review-errata.md) records what was refuted and why.

---

## 0. Development stage, and what it changes

**Owner context (2026-07-25): every story in the catalog was authored by the owner, and the only readers are the
owner's own children helping test.** There is no third-party author, no other family, no published cross-family
catalog, and no reader whose progress belongs to someone else. The risks below are real for the future; most are
not live yet.

That does not make the plan smaller. It **re-orders** it, and in a direction worth stating explicitly, because
the intuitive reading is backwards.

**Do the catalog-quality rules now, precisely because enforcement is currently free.** A8 (in-cell clone audit),
A14 (`L2-14`), B3 (`SR-9`) and A16-as-a-rule are all validator or CI gates over authored content. Today there
are 58 skeletons, no published cross-family content to grandfather, no external author to coordinate with, and
no reader to disrupt. Every month of authoring makes each of these strictly more expensive to adopt, because the
violating set grows and the fix list grows with it. The `L2-14` violation and the one clone pair are the
owner's own work to fix, which is the cheapest possible remediation posture. **These get more urgent, not less.**

> **Correction (2026-07-26).** An earlier revision of this paragraph said "the 37 `L2-14` violations". That
> conflated the unscoped count with A14's own band-scoping and overstated the fix list by 36. Re-measured by band:
> all 37 all-negative-valence decisions sit at **13-16 (4) and 16+ (33)**, and **zero** at 8-11 or 10-13. A14
> applies the negative-valence reading only at 8-11 and 10-13, where it is therefore **preventive with nothing to
> fix**, and the `death`/`capture` reading at 13-16 and 16+, where exactly **1** node violates
> (`the-quiet-harbor-protocol`). So A14's real fix list is one node, which drops its effort from M to S and makes
> it safe to land blocking on day one rather than advisory-then-flip.
>
> **Second correction (2026-07-26, on implementing it): the fix list is 5 nodes across 4 skeletons, not 1.** Both
> figures above came from a *static, direct-terminal* scan: a decision every one of whose options is itself a
> forbidden ending node. The rule as A14 actually specifies it follows single-choice corridors and runs over the
> reachable **configuration** space, which is deliberately broader and catches three cases the static scan could
> not see. Measured by running the implemented rule over the catalog: `the-quiet-harbor-protocol` `b_lo_final`
> (4 direct fatal terminals), `the-cinder-bazaar` `bg_hi_final` and `bg_lo_final` (a capture terminal plus
> corridors to death), `the-serpent-vaults` `c22_gate` (see the 6.2 correction), and `the-sunken-signal`
> `n_ascent` (at `air=0` both options kill). The last was missed even by the corrected static scan because it is
> MVP tier and therefore excluded from `_production_candidates`, though `load_skeleton` still validates it. All
> five were inspected and are genuine. Effort stays S for the *rule*; the content fixes are S4 work and the four
> skeletons are strict-xfail quarantined until then.
>
> **Third correction (2026-07-26, on fixing it): the fix list is 2 nodes across 2 skeletons, and the reduction came
> from narrowing my own rule.** The teen-band reading treated `capture` as fatal alongside `death`. That was an
> implementation choice, not the owner's instruction, which is specific: "a scenario where a user is presented
> option A and B and both result in death." Measured, the choice was doing real damage: **3 of the 5 violations
> existed only because of it**, and all three are deliberately authored espionage climaxes whose own beats read
> "Nothing between her and the closing dark", each offering a survivable `capture`. Capture is that genre's
> signature ending, not a death, and forbidding it would have rewritten four of the catalog's climaxes to satisfy
> a rule nobody asked for. Narrowed to `death`, which leaves exactly the two genuine cases, both
> resource-exhausted bottlenecks. **Both are now fixed and the quarantine is empty** (see A9's row for how).

**A19 (added post-#418) belonged in that list for a different reason: it was free because the defect was dormant.**
No theme contract declares a personalizable slot yet, so no fill carries a sentinel, so stripping them out of the
tokeniser changed no current output and needed no baseline re-derivation. **Delivered 2026-07-26**, and the
implementation confirmed the dormancy claim: the diversity regression gate reports `findings=0` unchanged. It also
shrank the defect: see the A19 row for the measured effect, which was far smaller than this plan first asserted.

**A20 (contract backfill) is authoring, so the stage argument cuts the other way from the gates above: it is not
free, and it does not get cheaper by waiting either.** It is the enabling precondition for personalization on 16
skeletons, and personalization is the one perceived-diversity lever that needs no new tree (section 8.1). With one
test household it is also the item whose benefit is most immediately observable, since the current readers can say
whether a book with their own name in it feels new.

> **A20 correction (2026-07-26, on starting it): the estimate of M was wrong by an order of magnitude. A20 is a
> program, not a task.** The measured scope is **4,341 `<<FILL>>` nodes across 16 skeletons, every one of them
> carrying zero existing `{SLOT}` tokens**, so there is no partial migration to finish anywhere: each skeleton is
> a from-scratch slotting pass over every beat, ending title, and theme-specific choice label it owns. The
> distribution is extremely uneven, which is the one piece of good news, because it means the item is divisible:
> `the-tenfold-siege` is 677 nodes and `the-sunken-temple`/`the-harrowstone-keep` are 550 each (and those two are
> A9's clone pair, so A9 subsumes their share), while the four smallest are 105, 32, 25, and 11. **Two skeletons are
> delivered:** `the-lost-mitten` (11 nodes, 16 slots) and `the-clocktower-cipher` (25 nodes, 26 slots), both passing
> all seven acceptance checks in `scripts/check_theme_contract.py`. The first was chosen to prove the toolchain end
> to end before committing to the large trees, and it did: `scripts/parameterize_skeleton.py` applied each slotting
> plan with the structural fingerprint unchanged and the gate unblocked. **14 skeletons and 4,305 nodes remain.**
> This does not change A20's priority argument above; it changes what scheduling it honestly costs, and it should be
> planned per skeleton rather than as one item.
>
> **Two authoring conventions the first two slices settled, worth following for the remaining 14.** First, the
> article belongs *inside* the slot value (`THRESHOLD` = "the old town clocktower"), matching all 45 existing
> contracts, which means a slot must never sit sentence-initially or the rendered beat opens lowercase. Four of
> `the-clocktower-cipher`'s beats did on the first pass and were restructured ("Gruff but kind, {KEEPER} warns ..."
> rather than "{KEEPER}, gruff but kind, warns ..."). Verify with a zero-count check over rendered surfaces, not by
> eye. Second, a theme-bearing ending title gets its own `ENDING`-scope `*_TITLE` slot rather than an inline token:
> `The {CIPHER} Revealed` would render as "The cipher Revealed", so the whole title is the slot. Generic titles
> ("Too Risky", "A Secret Kept") are left as literal text, though the parameterize script still requires an entry
> for every ending.
>
> **A21 (new, found while doing A20): 273 retired-theme proper nouns are hardcoded into 11 of the 45 skeletons
> that already have contracts, and the acceptance suite structurally cannot see them.** `legacy_lexicon` is only
> ever evaluated against a *proposed slot value* (`validator/slots.py`, the `legacy_lexicon` rule); nothing checks
> the skeleton's **own** residual text, so a proper noun left un-slotted in a beat, an ending title, or a choice
> label survives every re-theme intact. The confirming detail is that **270 of the 273 leaks name a term that
> already owns a slot on its own contract**, so those are migration misses, not design decisions:
> `the-clockwork-menagerie` declares `COMPANION` ("Tock the brass sparrow") then hardcodes `Follow Tock.` in 12 labels;
> `the-sky-ship-stowaway` declares `SHIP_NAME` and then ships the ending title `The Cirrus Sails On`;
> `the-pale-road` declares `C05_HAZARD`/`C06_HAZARD`/`C11_HAZARD` and then names those waypoints in 49 ending
> titles. The other **3 are the expensive kind**: `the-midnight-frequency` names `Okafor` twice and `Kettle` once in
> beats with no slot declared for either, so those need a contract change, not just a surface rewrite.
> A looser stem-based scan reports 1,771 hits, but that count includes generic English words that happen to
> sit in a lexicon (`salt`, `Roll`, `Register`, `Turning`), so **273 is the defensible number and the
> proper-noun class is the right bar to gate on**; the generic remainder is a judgement call per term, not a
> defect list. A21 is two pieces of work with very different costs: the *check* is S (a deterministic residual-leak
> scan over the same surfaces `parameterize_skeleton.py` already parses, added to the catalog drift guard so no
> future migration can repeat this), and the *fixes* are M and mostly mechanical, but not purely so, because
> substituting the full slot default is not always the right prose (`Follow Tock.` must not become `Follow Tock the
> brass sparrow.`). Land the check first, quarantine the 11 skeletons, then drain them.
>
> **A21 delivered 2026-07-26, check and all 273 fixes in one pass; the quarantine was opened and emptied in the same
> change.** `validator/theme_leak.py` is the scan, wired into both `scripts/check_theme_contract.py` (as check 7)
> and the catalog drift guard, and it found a fourth private copy of the slotted-surface walk on the way in: the
> walk now lives once, in `storybook/slotted_surfaces.py`, with `generation/binding.py`,
> `mutation/contract_gate.py` (whose docstring had *said* it reimplemented binding's private helper) and
> `scripts/parameterize_skeleton.py` all reading it. Fidelity was verified by rendering the pre-fix and post-fix
> documents under the same default binding and diffing every surface: **4 of the 11 came out byte-identical,
> including all 242 of `the-pale-road`'s substitutions**, because each waypoint's `C##_HAZARD` default was already
> exactly the leaked name. The other 7 changed 9 surfaces in total, every one deliberate and inspected. Two needed a
> contract change rather than a surface rewrite, which is the "expensive kind" predicted above: `the-clockwork-menagerie`
> gained `COMPANION_NAME` ("Tock") because binding the full `COMPANION` would have turned 9 short labels into
> `Follow her wind-up mouse Tock.`, and `the-midnight-frequency` gained `ROUTE_C_KEEPER`/`ROUTE_D_KEEPER` for the 3
> unowned leaks. **The case-sensitivity decision paid for itself immediately**: `the-midnight-frequency`'s harbor-office
> beat opens "The harbor office: kettle, charts", and a casefolding scan would have reported the appliance as a leak
> of the librarian `Ms. Kettle`.

> **A9 correction (2026-07-26, on investigating it): "clone pair" was wrong, and A9 is two items whose efficient
> routes point in opposite directions.** Measured: **every `structure_features` field of the two books is identical**
> (550 nodes, 152 endings, 801 choices, `max_depth` 58, `mean_branching` 2.892, the same ending-kind and valence
> histograms, `branch_and_bottleneck` both) **except `n_effects`, 49 vs 48**. But the prose is *not* duplicated:
> **1,326 of 1,503 slotted surfaces differ**, the `structure_fingerprint`s are unequal, and the two books declare
> different variables (`scout_ally`/`has_sigil` vs `marsh_guide`/`choir_key`). Book 2 is a **re-skinned skeleton, not
> a copied story.** That inverts the disposition: the writing is not the substandard part, the design is, so
> **replacing book 2 would discard 1,326 distinct authored surfaces to fix a problem that is not in them.**
>
> **Item 1, the 14 SR-9 findings: one root cause, fixed at one node. DELIVERED.** The 14 are not 14 defects; they are
> the cross-product of `has_sigil` (2 values) x `vigor` (7 values) over a single condition, `has_lantern=False` on
> entry. Book 2 declares `has_lantern: true` as its own initial and **gates two choices on it while granting it
> nowhere**, so a reader who finished book 1 without the lantern arrives to two dead branches (`L2-11` at `g0_hedda`
> and `g2_cu1`). Book 2 already had an unwired `g0_lantern_buy` node, so the fix was to make that node's single
> choice carry `set has_lantern=true` and to widen its beat to cover both arrivals. **Deliberately unconditional:** a
> gate on `has_lantern==false` would itself be dead from book 2's own declared initials, mirroring the exact defect
> SR-9 flags, whereas setting an already-true bool is a no-op. Series errors 14 -> 0, `run_gate` still unblocked.
> Note the honest side effect: the added effect moved `n_effects` 47 -> 48, so the structural distance *fell* from
> 0.000947 to 0.000469. Fixing item 1 made item 2 marginally worse by the metric.
>
> **Item 2, the structural twinning: restructure book 2, do not replace it. Effort L, not started.** Three routes
> were considered. *Replace* is the worst: 550 nodes of new prose thrown at a shape defect. *Metric-gaming* (nudging
> features until the distance clears `tau_cell` without changing what a reader walks) is cheapest and is **rejected
> explicitly**: it would convert a real perceived-diversity defect into a passing number, which is the failure mode
> this whole plan exists to stop. *Restructure* is the only honest route that preserves the prose, and it is genuine
> editorial work: a middle book of a series should not be a 152-ending, 58-deep sprawl shaped exactly like its
> opener, and making it a tighter hand-off book moves `n_nodes`/`n_endings`/`n_choices`/`max_depth` together (the
> numeric term carries weight 0.5). This is authoring hours, not engineering, and it is the one A9 piece that stays
> open.

**A9 is unblocked.** The clone pair can be retired and replaced outright with no migration concern, because the
only progress recorded against it is test data belonging to the owner's family.

**The reader-protection machinery is genuinely premature.** A15 (retire without deleting progress), A17
(tombstone card), and the deferred visibility-ceiling work all protect a reader whose collection is not the
owner's to discard. Today it is. These should be recorded as **triggered**, not scheduled:

| Deferred item | Trigger that makes it live |
| --- | --- |
| A15, A17 (progress preservation, tombstones) | The first reader outside the owner's household, or the first book the owner would be unwilling to reset |
| A16 (no retiring a non-final series book early) | Same. Keep it as a **written rule now**, since it costs nothing and prevents a habit forming |
| Visibility ceiling, ring-2 attribution | The first connected family |
| Reading telemetry (`r1-deferred-debt-register` U5) | Enough readers for a distribution to mean anything. With one family it cannot calibrate anything |
| A10 (empty teen `short` cells) | A request that actually lands in one. The owner controls requests today |

**And the child-reader findings can now be tested rather than argued.** The subagent review in section 6.1
reasoned about what a child would find confusing. The owner's children are the current test readers, and the
repo already ships `.claude/skills/naive-ux-check/` for exactly this: staged naive-user comprehension prompts
per persona, logged to a dated findings report. Three of that review's judgements are empirical questions a
single session with a real child would settle better than any amount of analysis:

- Does a 3-hop rewind read as "the app took my turn"? (A13b's core risk)
- Is the lower back-chevron confusable with the one that exits the book? (A18)
- Does a hero-name field with a shuffle land as a toy or as a restriction? (A11)

Run those before building A11, A13b or A18, not after. It is the one form of evidence this plan has been unable
to gather, and it is currently available.

---

## 1. Basis: what is established

Each of these was re-derived independently, from source, by a reviewer instructed to refute it. Nothing else in
this document is treated as established.

| Fact | How verified |
| --- | --- |
| 61 skeletons, 58 production-eligible | `is_sidecar` + `_production_candidates` |
| 24 `(band, length, style)` cells, 6 empty, and **15 of 18 non-empty cells hold exactly three trees** | `candidates_for_cell`; forced by 15x3 + 2x4 + 1x5 = 58 |
| **No `short` skeleton exists for `13-16` or `16+` in either style**, so those requests have zero candidates | cell enumeration |
| P(a reader's second story reuses the first's tree) in a 3-cell is **exactly 1/5**; general form 1/(2n-1) | closed form, plus 4M trials against the real `select_skeleton_for_cell` |
| `the-harrowstone-keep` and `the-sunken-temple` are **graph-isomorphic** (start- and ending-kind-preserving, 550 nodes, 796 edges), in one cell, both production-eligible | colour refinement + pruned `DiGraphMatcher`; WL hashes equal |
| `structure_fingerprint` cannot detect that pair (355 of 550 node ids differ) | direct comparison |
| The catalog declares **132 curated `metadata.themes`**; **zero** are values in `_THEME_TAG_MAP` (which is 67 keys to 12 values) | enumeration |
| **The zero overlap was a category mismatch, not a missing map entry.** The echo map's 12 values are concrete **subjects** (`dragon`, `castle`, `space`); the 132 curated themes are abstract **authorial themes** (`courage`, `friendship`, `mystery`). Two different axes, so no synonym-mapping inside one flat space could make them intersect | A1 implementation; enumerated both value sets |
| **The story side barely populates the subject axis, which is the request side's native language.** All 15 canonical theme tags appear on some story, but **9 of 22 subject tags never appear on any story**: `animals`, `castle`, `cave`, `dinosaur`, `dragon`, `fire`, `knight`, `magic`, `pirate`. Eight are echo-vocabulary values, meaning the echo map exists precisely because we expect children to ask for exactly the things no story is tagged with. **So A1 and A2 fix the mechanical defects but cannot fix matching for those requests: the signal is absent from the corpus, not mis-measured.** A catalog tagging gap, cheap to close because it is metadata rather than prose; pair it with A20 | `scripts/measure_theme_coverage.py` section 4 |
| The similarity comparison is **asymmetric**: the stored side is premise tags union raw curated themes, the request side is premise only, so symmetric Jaccard scores a byte-identical premise at **0.333** against `tau_theme` 0.35 and it does not register as similar | `history.py:190` vs `query.py:197`; reproduced |
| `DifferentiationLevel` never reaches `fill_skeleton`; it reaches a warning, a log line, and the flywheel trigger | call-graph trace |
| The ATG is advisory, fail-open, single-partner, with an empty per-band threshold table | `moderation/leaf_diversity.py`, `diversity/leaf.py` |
| Ending **count** and satisfying **path mass** are decoupled (Spearman weak, and negative under 3 of 4 reader models) | 4 reader models; walker validated in lockstep against `StoryEngine`, 0 divergences in 1,800 walks |
| Topology does **not** key satisfying path mass (4 of 6 classes hold zero gamebooks; the 2 populated classes do not separate, eta-squared 0.367, and the direction is reversed). The **fail-kind mix** does (eta-squared 0.636) | per-skeleton measurement |
| 1,778 gamebook endings; 178 sit below 33% of `min_complete`, splitting 104 `setback` / 73 `death`+`capture` / 1 `discovery`; scoped to foreclosing terminals, **no** skeleton breaches `min_endings` | BFS depth + `_effective_floors` |
| The **shared opening spine is 1 to 6 nodes** (median 3), and within-cell opening-content Jaccard is median 0.089, so two books in a cell were never confusable at the opening | dominator intersection; pairwise content Jaccard |
| **Go back ships, works at an ending node, and is disabled for continuation reads** | `engine.ts:325-347` (`back` has no ending guard, requires only `path.length > 1`); `engine.ts:288-297` fails closed when `path[0] !== start_node` |
| Of the 73 shallow foreclosing terminals, **only 15 are escapable by a single Go back**; the other 58 are reached from single-choice corridors, so backing up one step re-presents the same fatal choice | per-terminal predecessor analysis |
| **All 73 are within 3 Go-back hops** of a node offering a real alternative (15 need one hop, 58 need exactly three; max 3) | back-walk to nearest branching ancestor |
| Across 58 production-eligible skeletons there are **2,668 decision nodes** (non-ending, 2+ choices). **144** have every option terminating, but those sit at **median 90% of the tree's max depth** and **88 of them offer a positive ending**: they are climaxes. **37** are all-negative-valence. **1** has every option a `death`/`capture` terminal (`the-quiet-harbor-protocol`) | per-node target classification |
| Separately, **776 single-choice nodes** lead only to a `death`/`capture` terminal. These are not decisions; they are the corridor pattern A13 addresses | per-node scan |
| `save_slots` is client-writable, server-persisted, and **omitted from `validate_reading_state`** | `schemas.py:80`, `reading.py:412`, `reading.py:168-175` |
| **129 of 132 catalog themes pass the echo floor at band `3-5`** | ran the real `sanitize_element` (`story_requests/interpretation.py`) at all six bands; re-run unchanged after PR #418, same three withheld (`lethal checkpoints`, `lethal missteps`, `the drowned descent`) |
| **45 of 61 skeletons have a `.contract.json`; 39 of those 45 declare a `HERO` slot**, so 16 skeletons have no contract at all | enumeration of `skeletons/**/*.contract.json`; independently stated in ADR-023 and reproduced here |
| Beats hardcode character pronouns, so a slot value cannot vary gender: `the-cinderwick-exchange.json:89` "the retired clocksmith who tends the lo[ck]", `the-envoy-of-three-courts.json:135` "See {COURIER} on **his** way and snatch some sleep" | direct file read |
| The ATG had **no sentinel awareness** (fixed 2026-07-26, A19): `strip_sentinels` was imported by `validator/reading_level.py`, `moderation/pipeline.py` and `moderation/rescreen.py`, and by nothing under `diversity/`. **The end-to-end effect was much smaller than first claimed**: on the two committed pilot fills with 113 and 108 sentinel sites, unigram distance did not move at all and bigram distance moved by ~0.006, flipping no verdict. See the corrected A19 row for why, and why it was still worth fixing | import scan; end-to-end run over `out/pilot/fills/` |
| **`HERO` is the catalog's least varied slot**: 39 contracts bind it to **28 distinct values** (ratio 0.72), with `Wren` reused 5 times and `Rowan`, `Milo`, `Priya`, `June` each reused | `default_binding` enumeration across all 45 contracts |
| **Every non-personalizable differentiating slot is at or near fully distinct**: `THRESHOLD` 34/34, `ENTRANCE` 24/24, `DEADLINE` 19/19, `GOAL` 17/17, `DEADLINE_SIGN` 17/17, `OPENING_MOMENT` 16/17, and all three `ROUTE_*_CHAR` at 1.00 | same enumeration, slots appearing in 8+ books |
| **`COMPANION` is fully distinct (14/14)** and is personalizable under ADR-023 row 3, so it is the one slot where opting in spends a maximally differentiating axis | same enumeration |
| **Theme-contract coverage is anti-correlated with band**: `5-8` and `8-11` at 100%, `3-5` at 86%, but `10-13` 64%, `16+` 64%, `13-16` **57%**. 16 of 61 skeletons have no contract, 15 of those 16 at `10-13` and above | per-band `.contract.json` existence scan |
| **Both books of the isomorphic clone pair lack a contract**, so `the-harrowstone-keep` and `the-sunken-temple` are ineligible for personalization entirely | contract existence check on both slugs |
| Reading telemetry does not exist: `ReadingState` is one mutable row with `path` overwritten; `Completion`'s key includes `ending_id` with one `found_at`, so re-reads and depth-at-terminal are unrecorded | `db/models.py:725-793` |
| Difficulty, win-arc count, and reading telemetry are unspecified corpus-wide | 98-document survey |

## 2. What this plan does NOT claim

Recorded so these are not re-derived. Full reasoning in the errata.

- **No funnel argument.** The shared spine is 1 to 6 nodes and same-cell openings are already distinct, so
  "a reader who exits early has read only the shared opening" is false. Any depth floor must be justified as a
  **difficulty** decision, not a diversity one.
- **No fraction is recommended for a depth floor.** The 33% figure came from a circular proxy.
- **No per-topology outcome floor.** Not calibratable.
- **No claim that a satisfying-path-mass figure near zero is a defect.** Under a competent reader it is
  1.3% to 34.9% (median ~9%), and two or three plies of foresight move 13 of 14 skeletons to 41-100%.
- **No claim that `save_slots` lacks a producer**, that `LEGAL_TRANSITIONS` has no exit from `published`, or that
  the COPPA remediation plan is missing. All three were false.
- **No new snapshot-based restart mechanism.** Path replay already ships and is now the normative mechanism:
  `runtime-semantics.md` section 6 was revised 2026-07-26 by
  [ADR-024](adr/adr-024-bounded-backtracking-path-replay.md) from "no backtracking" into "backtracking by
  forward replay only", which prohibits computing an inverse. The conclusion is unchanged and now rests on a
  rule rather than on a deferral.
- **No `min_positive_endings` floor**, and no assertion that any coverage target is achievable before it is
  measured.

## 3. Track A: near-term, grounded

Each item traces to a fact in section 1. Effort: S under a day, M a few days, L a sprint or more.

| ID | Deliverable | Effort |
| --- | --- | --- |
| **A1** | **DELIVERED 2026-07-26. Two vocabularies, not one grown map.** `_THEME_TAG_MAP` is frozen as the **echo** vocabulary with a `#CRITICAL` note and a test pinning its 12 values, because `worker.py::_degraded_set_aside_decisions` reads them back to a child. The new `diversity/similarity_vocab.py` holds the similarity vocabulary; `similarity_signature()` uses it and **drops** an unrecognised curated theme instead of passing it through verbatim, which is the line (`normalize.py` `tags.add(_THEME_TAG_MAP.get(lowered, lowered))`) that put 132 unproducible strings on the stored side. **Coverage measured, not asserted** (`scripts/measure_theme_coverage.py`): **131 of 132** distinct catalog themes map (99%), **256 of 257** theme uses (100%); the single drop is `state-gated locks`, excluded deliberately as a graph property rather than a theme. Empty request signatures over the A4 panel fall from **7 of 16 to 1 of 16**. One finding that reframes the defect: the echo map's 12 values are **concrete subjects** and the 132 curated themes are **abstract**, so the zero overlap was a category mismatch, not a missing entry. The similarity space therefore spans both axes (22 subject + 15 theme = 37 canonical tags). | M |
| **A2** | **DELIVERED 2026-07-26. A containment measure**, `containment(request, story) = \|request & story\| / \|request\|`, in a new function. `jaccard_similarity` and its documented empty-set semantics are untouched. The plan's 0.333 case is **reproduced as a test** rather than asserted: one request tag plus two curated themes the request side cannot produce gives Jaccard exactly 1/3 against a 0.35 floor, so the match was missed; containment returns 1.0. Argument order is load-bearing and carries a `#CRITICAL` note, since swapping it inverts the question to "how much of this story did the reader ask for", penalising every rich story. Empty request returns 0.0, matching the WS-0 intent that an empty signature never registers as similar. | S |
| **A3** | **DELIVERED 2026-07-26. A saturation ceiling guard** (`_SATURATION_CEILING = 0.999`) plus a regression test pinning that saturation reaches exactly `count/3` in a 3-tree cell, so the pinning behaviour cannot drift silently. A2 pushes harder toward "similar", so the cell reaches 1.0 sooner, and above the ceiling the ladder moves past `TREE` rather than continuing to recommend a tree that does not exist. | S |
| **A4** | **DELIVERED 2026-07-26. A committed premise panel** of 16 realistic child requests (`scripts/measure_theme_coverage.py::PREMISE_PANEL`), spanning pets, sports, family, school, music, invention, weather, food and siblings plus the fantasy staples the echo map anticipates. Coverage is printed with no target asserted in advance, per the method rule. | S |
| **A5** | **DELIVERED 2026-07-26. `tau_theme` re-derived: 0.35 to 0.34**, recorded in `query.py` with its basis. The old value no longer meant what it was set to mean, because A1 changed the measure's *input* and A2 changed the *measure*. Measured containment over the panel by catalog (976 pairs): median 0.0000, p90 0.3333, max 1.0000; 0.34 sits just above p90, admitting a request whose themes are largely delivered while rejecting the long tail of single-tag coincidences. Deliberately not tuned to a target rate. | S |
| **A6** | **DELIVERED 2026-07-26. Thread `DifferentiationLevel` and prior-fill context into `fill_skeleton` and `fill.md`.** The signal used to reach a warning string, a log line and the flywheel trigger, then stop; the fill that could act on it never saw it, so escalating a request changed nothing about the prose. Now persisted by `authoring_plan.py` into `authoring_metadata` (`differentiation_level`, `prior_titles`, `prior_theme_tags`, `variation_axis`), read by `worker.py::_differentiation_directive`, rendered by `prompts.build_differentiation_directive`, and threaded through `fill_skeleton` into a new trusted `{differentiation_directive}` block in `fill.md`. The three levels render distinguishably (pinned by test) and an absent signal says so rather than implying the structure is new to the family, which matters on the admin-override path where no similarity context is computed. **The privacy fence holds structurally, not by discipline: `authoring_metadata` has no key for a prior premise**, so a sibling's request text cannot travel into this fill even by mistake. Only published titles (content the family already holds) and closed-vocabulary theme tags cross. The block is rendered **outside** the `UNTRUSTED_USER_INPUT` fence, since it is pipeline instruction, and a test asserts that position. | M |
| **A7** | **DELIVERED 2026-07-26. A variation-axis library** (`generation/variation.py`): ten authored craft axes across narrative distance, sensory emphasis, tonal register, viewpoint favour and pacing, one drawn per request. Drawn **deterministically** via blake2b over the request id, not `random`, because Python salts string hashes per process and a randomly-drawn axis would confound every before-and-after comparison of its effect. Each instruction is a positive craft direction rather than a prohibition (pinned by test), since a prohibition tells a model what to avoid without telling it what to do instead. One axis per fill, never several: a fill told to be simultaneously close-third, sound-led, slow-paced and antagonist-sympathetic has four masters. No axis changes what happens or how a story ends, only how a fixed sequence of beats is narrated, which is what keeps it inside the band profile. **Verification limit, stated rather than glossed:** the plan asks that RL-13 not regress "over regenerated fills before and after", and that cannot be checked here because it needs real provider calls. The reading-level suite passes and the axes are *designed* to hold register fixed by varying an authorial decision instead of sampling temperature, but the empirical check is outstanding and belongs with the first real generation run. | S |
| **A8** | **DELIVERED 2026-07-26. In-cell clone audit in CI**, using `structural_distance` (not `structure_fingerprint`, which cannot see a renamed clone) against the **loaded** `TAU_CELL` from `ws5_floor_baseline.json`, never a hardcoded 0.05. Logic in `diversity/incell.py`, CLI in `scripts/check_incell_clones.py`, wired **blocking** into `ci.yml`'s existing `diversity` job. Measured 67 distinct in-cell pairs across 18 populated cells: exactly one breaches, the known clone pair at 0.00095, and it is allowlisted against A9. The allowlist is a shrinking debt register, not an exemption regime: the gate also fails on a **stale** entry, so a fixed pair must be deleted in the same change. One counting defect found and fixed while building it: style partitions a cell only at `13-16` and `16+`, so a naive style loop measured every lower-band pair twice (the origin of this plan's earlier "100 pairs across 28 cells", which also contradicted its own established 18-cell figure). | S |
| **A9** | **Resolve the in-cell duplicate** under the disposition principle in section 6, fix-or-replace with no series exemption. Bound by A16: `the-harrowstone-keep` and `the-sunken-temple` are brass-lantern books 1 and 2, a deliberate series stress-test artifact, so "retire one" is not available. **Corrected and split 2026-07-26, see the A9 note below: it is two items with opposite economics, and "clone" was the wrong word.** Item 1 (the 14 SR-9 findings) is **delivered**; item 2 (the structural twinning) is a restructure of book 2's shape, effort **L**, not started. | M -> L |
| **A10** | **Make the empty teen `short` cells fail gracefully or fill them.** A `13-16/short` or `16+/short` request has zero candidates today and 422s. Per the disposition principle in section 6, authoring is preferred over degrading the surface. | M |
| **A11** | **Set expectations on the request page, affirmatively, and drop two of the three restrictions.** `RequestStory.tsx` is one prompt and a 500-character box today. Per the child-reader review (section 6.1): **drop** the fixed-structure statement from the kid surface (no child under about eleven has that model; keep it on guardian intake) and **drop** "some themes are off for this family" (unnameable on the kid surface, so it is a pre-emptive accusation with nothing to act on; the existing blocked-status copy handles the real event kindly). **Reshape** the naming rule from a prohibition into a mechanism: a "Who's the hero?" field pre-filled with a made-up name and a shuffle control, which sets the expectation without ever saying "you cannot be the hero". **Copy superseded by ADR-023 (merged in PR #418); adopt its wording, do not draft alternative text.** The child-reader review's suggestion to reuse `interpretation.py`'s "Heroes in our stories always have made-up names" is **withdrawn**: ADR-023 section 4 is replacing that exact sentence, because it becomes false for a family that enables G18, and the affirmative PII line this row previously proposed ("Everyone in the story gets a made-up name, even your friends") is false in the same state. ADR-023 section 4 Ask 1 supplies the replacement and asks this plan to adopt it rather than converge separately; the load-bearing change is "starts with", which is unconditionally true because *generation* always uses a placeholder, and which stops implying the separate claim about what a reader *sees*. Kid surface: "Everyone in the story starts with a made-up name, even your friends. Ask your grown-up if you want your own name to show up when you read." Guardian help text as given in that section. **Add** the expectation the review found matters most to a child and that was on nobody's list: "A grown-up reads your idea first. Then it takes a little while to write your book." Net effect is zero new blocks of rules text. Serve the guardian-facing set from the API off `ReasonCode` / `band_profile` / `content_nogo`; the kid-surface response still omits `content_nogo` values entirely. **Shuffle semantics (ADR-023 Ask 2, answered here): display-only, among generic names, with no effect on what is generated or stored.** The field picks a label for the request surface; the skeleton's `HERO` slot is bound by the fill, and under ADR-023 personalization is a render-time substitution on the family's own devices. Making the shuffle write a stored bound value would put it on the same slot the personalization sentinel occupies and force the two to be sequenced; keeping it cosmetic leaves them orthogonal and needing no coordination. This also keeps the naive-UX question in section 0 ("toy or restriction?") a pure copy question. Update `capability-register.md` K19 (line 137), whose row already records this copy dependency as a precondition on G18's flag, and note that K20/G18 are minted (register v1.8) so the hero-name surface must stay consistent with them. | M |
| **A12** | **Enable Go back in continuation reads.** `replayRecordedPath` fails closed when `path[0] !== start_node`, disabling Go back in exactly the state-carrying series books where a reader has most to lose. **Rescoped 2026-07-26 (S0/B2 finding): this is not a bug fix, and it is deferred behind a decision.** Replaying a continuation read needs its origin's initial variables, and nothing retains them: `startContinuation` seeds `var_state` from a carried map but the resulting `ReadingState` does not keep it, `ReadingState` has no column for it (`db/models.py:725`), and `Completion` stores only `(child_profile_id, storybook_id, version, ending_id, found_at)` so the predecessor's exit state cannot be re-derived either. The seed reaches the client only transiently through router `location.state`, which `series.ts` documents as untrusted and attacker-shapeable. So enabling it needs new durable state, hence a schema change, an API change and an OpenAPI regeneration; **and that state would be a replay origin, making it a state-restoration input of exactly the class B1 describes.** Built naively it creates a second `save_slots`, letting a forged origin replay into a state the reader never earned, in the books where that pays best. ADR-024 Decision 6 records it as not authorized and states the fail-closed-validation requirement any future decision must meet. | L, deferred |
| **A13a** | **Leave the in-story Go back exactly as it is: one step, always available.** `Reader.tsx:210` states its purpose, "Kids mis-tap constantly; Go back undoes just the last choice." A multi-hop rewind bound to that button would move a mis-tapping 4-year-old three passages upstream and erase prose they were enjoying. At 3-5 and 5-8 that is pure loss, since `_PROFILES` forbids `death` and `capture` at both bands so there is no fatal corridor to rescue, and a 3-5 story is 10-45 nodes, making 3 hops up to a third of the book. **No change to `back()` or `canGoBack()`.** | none |
| **A13b** | **Add a second, separately labelled affordance at the ending screen only: "Try a different way."** Walks up to **3 hops** to the last node where the reader had a real pick, and **falls back to one step when there is none**. Availability stays exactly today's `path.length > 1` and replayable: it must never become "an untaken choice exists within 3 hops", because that hides the button at precisely the 88 preserved climaxes (take option A, die, go back, take option B, win: on that second ending there is no untaken fork nearby and a button the child just learned would vanish). "Untaken" is defined against the current read only, and the walk stops at the **first branching ancestor** regardless of whether its other options were used, so the destination is always "the last place you got to pick" rather than a distance that varies per press. Captures the full measured benefit (the 58 corridor terminals) without repurposing a learned affordance. | M |
| **A14** | **DELIVERED 2026-07-26. `L2-14`: no decision may offer only fatal options, band-scoped, stated so it cannot be dodged.** Owner rule: a reader must never be shown option A and option B where both end in death. Implemented in `validator/layer2.py` as an ERROR over the reachable configuration space. **(a) Band-scoped.** `Valence.NEGATIVE` includes `setback`, so a single negative-valence rule would forbid a 15-year-old from ever facing a lose-lose dilemma, which is what a `gauntlet` reader seeks and what ADR-011 section 5 sanctions from 13-16 up. Negative-valence reading at **3-5 through 10-13**, `death`/`capture` reading at **13-16 and 16+**. (Plan text originally scoped the broad reading to 8-11 and 10-13 only; extended to 3-5 and 5-8 deliberately, since it adds zero violations there, is strictly more protective for the two bands the child-reader review found got no benefit, and the scoping rationale only ever argued against over-constraining teens.) **(b) Stated over the reader-visible decision unit, not the node**, or an author complies by splitting an all-fatal decision into two single-choice corridors that each end fatally: the rule passes and the child gets a page with one button that kills them. So: a reachable configuration with 2+ visible choices fails when **every** option reaches a forbidden ending with no intervening visible choice. That folds in the 776 single-choice fatal corridors, which are the larger agency problem. Layer 2 because it is about visible choices in reachable configurations. **Fix list: 5 nodes across 4 skeletons** (see the section 0 second correction), strict-xfail quarantined pending S4. | S |
| **A15** | **Triggered, not scheduled (section 0).** **Retire-for-quality must not delete a child's progress.** `archive` is the only exit from `published`, `library.py` filters on published status, `reconcileOfflineCache` purges the local copy, and `reading_history.py::_history_item` degrades a version-less book to a storybook **id** as its title with `total_endings = 0`. So a retired book takes the shelf card, the in-progress read, the offline copy and the "6 of 7 endings found" badge with it, silently. Distinguish **unsafe** (archive now, the urgency justifies it) from **substandard** (no new readers: stop assigning, keep it readable for any profile with progress or completions, let it age out). Interim before the deferred visibility work exists: unassign only from profiles with no activity. Fix `_history_item`'s degraded row to show a friendly retired label, not a UUID. | M |
| **A16** | **Adopt as a written rule now, enforce when triggered (section 0).** **Never retire a non-final series book before its replacement ships in the same release.** `Reader.tsx:313-320` offers "Continue the series" on a satisfying ending of a non-final book; if book 2 changes or goes, that promise goes quiet with no in-product account, after a teen spent hours in a 550-node book and earned carried state. The replacement must accept book 1's carried state, which is exactly what B3 gates. If it cannot, re-cut book 1 to `is_final` so the continuation is never promised. Binds A9. | S |
| **A17** | **Triggered, not scheduled (section 0).** **A retired book leaves a tombstone, not a hole**: title, endings the child found, and one line ("This one has gone back to the workshop. Your 6 endings are still yours."). Children infer causes, and a card that vanishes next to a `StarRating` they cannot clear invites "did I lose it because I rated it 2 stars?". | S |
| **A18** | **Differentiate the two back-chevrons.** `Reader.tsx` renders Go back as a ghost button with a chevron visually identical to the top-bar "Leave" chevron, one of which exits the book. A13b makes the lower one more consequential. Give the story-level control a circular-arrow glyph, and make the ending-screen affordance primary weight rather than ghost, since there it is a headline action. | S |

## 4. Track B: defects found by the review, independent of this plan

Each stands on its own and does not wait on Track A.

| ID | Defect | Effort |
| --- | --- | --- |
| **B1** | **DELIVERED 2026-07-26.** `save_slots` was the only reading-state field omitted from `validate_reading_state` (`reading.py:168-175`), defeating the `#CRITICAL` anti-forgery intent stated two lines above the call site. Resolved **fail-closed**: the gate now receives the field and refuses any non-empty slot map. Chose refusal over content validation because the field has **no producer and no consumer** (the client initialises it to `{}` and only copies it through, and `ReaderPage.tsx:285` records that "the engine never mutates it today"; the server only round-trips it at `reading.py:79`/`:412`), and because `runtime-semantics.md` section 5 specifies the field normatively as "slot name to snapshot" without ever fixing the snapshot's shape. Validating slot contents would therefore mean inventing a schema here and pinning future work to it, while refusing a non-empty map costs nothing today and turns the moment slots go live into a loud 422 pointing at the check. That is the bar ADR-024 Decision 6 sets for a state-restoration input. The parameter is deliberately **required, not defaulted**, since a default is how the field came to be skipped in the first place; all 18 existing call sites were updated. | M |
| **B2** | **DELIVERED 2026-07-26.** `runtime-semantics.md` section 6 stated there is no back button in v1 and that any implementation "requires a revision to this document and an ADR", while `Reader.tsx:210` shipped one. Resolved by [ADR-024](adr/adr-024-bounded-backtracking-path-replay.md) (Accepted) plus the section 6 rewrite (document version 1.2). The finding that mattered: section 6's *rationale* was the wrong part, not just its rule, because the shipped mechanism replays forward and never inverts an effect, so the snapshot model is preserved and the event log section 6 waited for is not needed. ADR-024 also authorizes A13b and, per the A12 row, declines to authorize continuation backtracking. | S |
| **B3** | **DELIVERED 2026-07-26 as `SR-9`.** For `carries_state=true`, every satisfying-ending state of book N must be an admissible entry state for book N+1. Layer 2 only ever walked from `start_node` with declared initials, so continuation entry state was outside every existing rule's view; `walk_configurations` and `validate_layer2` now take an optional `carried` seed, and `StoryEngine.start_continuation` mirrors the client's `startContinuation` including its order of operations (carry-seed **before** the entry node's `on_enter`, since seeding after would let a carried value overwrite an effect the client applies first, and player/validator divergence is a conformance failure). Reports two failures: an **L2 error delta** (any error the receiving book raises from the carried entry but not from its own declared initials, which is the F3 shape) and **unwinnability** (no satisfying ending reachable, which `L2-10` cannot see because it asks whether *some* ending is reachable, not a satisfying one). Bounded at 64 distinct exit states per pair, and it says so rather than reporting a clean chain over a truncated sample. Checked against #416's `SR-8` before building: that rule is a static comparison of two declaration blocks, this one simulates reachable state, so they do not collapse. | M |
| **B4** | `machine.ts:108` resets to the start node with declared initials, so "Read again" in a continuation read fabricates `has_lantern=true` and `vigor=5` the reader never earned and discards carried state. | S |
| **B5** | **DELIVERED 2026-07-26, by `SR-9`.** F3 is escalated from authoring guidance to a gate-detectable defect, and **confirmed firing on real content**: run against the committed `brass-lantern` chain, `SR-9` raises **14 errors**, every one of them a book-1 win state carrying `has_lantern: False` into a book 2 that then breaks. That is B5's claim reproduced by the gate rather than by inspection. Consequence worth stating: the chain can no longer pass `publishing/service.py`'s approval-time series check until the content is fixed, which is the intended effect and lands on the same two books A9 is already repairing or replacing. **Evidence updated 2026-07-26: those 14 errors are now FIXED** (A9 item 1), so re-running `validate_series` on the `brass-lantern` chain today reports **0**, not 14. The gate is not broken; the content it caught has been repaired. The 14 were one root cause enumerated over `has_sigil` x `vigor`, and the fix was one choice in `the-sunken-temple`'s `g0_lantern_buy`. Anyone re-deriving B5's evidence must read book 2 at commit `e0e6c3a^` to see the gate fire. | S |
| **B6** | **Closed as working-as-intended** (section 6): sharing a child's first name with a connected family is sanctioned by mutual guardian consent. Residual **re-scoped by PR #418**: ADR-016 now carries a proposed addendum that already names this item, and ADR-023 section 4 requires that ADR-016 be amended in **one** edit covering both ring-2 *attribution* granularity (this item) and ring-2 *personalization* granularity (ADR-023 section 3), which sets a deliberately stricter bar for the same datum. So the residual is no longer "add a sentence"; it is **participate in that single reconciliation edit and do not race it**. Whoever writes the amendment writes both halves or neither. The asymmetry is recorded as intended, not as an inconsistency to resolve: an attribution line is one low-bandwidth fact rendered once to a receiving *guardian*, while a name substituted through story prose is the same datum delivered continuously to another household's *children* and compounded with other slot values. | S |

## 5. Deferred, each behind a named prerequisite

Not "later" in the abstract. Each has one thing that must happen first.

| Item | Prerequisite |
| --- | --- |
| Reading telemetry (depth reached, early-exit rate, real satisfying rate) | A schema design for durable per-session reading data plus a child-behaviour privacy review. `r1-deferred-debt-register.md` U5 already registers this as Phase 4b with an owner; extend that, do not duplicate it. |
| A fail-depth floor (`PL-25` if it is ever built; `PL-22` is the maximum on `main` and open PR #416 takes `PL-23` and `PL-24`) | **Probably not needed at all** if A13 lands: a multi-step Go back fixes all 73 shallow foreclosing terminals with no skeleton edits, where a floor needs 73 relocations and a fraction with no non-circular basis. Revisit only if A13 is rejected or telemetry shows a residual problem. |
| An outcome-mix floor keyed on the fail-kind mix | Telemetry. Do not key it on topology. **Partly overtaken by PR #416's `PL-24`** (advisory ending-mix shape: a 60% single-kind ceiling plus a style-aware winnability floor). That covers the *distributional* half of this item without telemetry, so the residual here is only the fail-kind-mix keying, which still needs telemetry. #416's own calibration note is the more valuable carry-forward: a flat 5% positive-valence floor fired on all nine gamebooks and no prose story, so it was replaced with an absolute distinct-winnable-endings floor for gamebooks. That is section 7 rule 2 arrived at independently. |
| Challenge mode / permadeath | B2's ADR, since it is a backtracking-semantics change; plus a per-(profile, series) row, which does not exist. |
| Alternate beat phrasings | Its own design doc and ADR. The evidence for it is weaker than stated (the illustrating quotation was wrong), though the byte-frozen-beat constraint is real. Also bounded by the `L2-12` 100,000-configuration cap, which permanently caps declared variables near five. |
| Per-reader (`profile_id`) scoping, and ATG against the k nearest same-tree fills with calibrated thresholds | A1 through A5, since both consume the similarity signal. |
| A guardian visibility ceiling | A first-class ceiling column on `Storybook` (no `Storybook` to `StoryRequest` join exists; `GenerationJob.storybook_id` is deliberately not a foreign key), plus an explicit amendment to the `#CRITICAL` invariant at `publishing/service.py:309-317` that visibility "must never be settable outside an admin-gated approve". If built, enforce on an explicitly passed acting capacity per `admin-guardian-dual-roles-plan.md`, not on `acting_role`, which returns `GUARDIAN` for a same-family admin approve. |
| Growing the small cells past three trees | WS-8's flywheel owns the automated path; A8 must gate every addition. |

## 6. Decisions required

**Resolved (owner, 2026-07-25): catalog disposition.** No book or skeleton is required to be kept. Retire and
replace, or fix; substandard work is not carried. This is a standing principle, not a one-off ruling on
brass-lantern. **Convergent, narrower support from ADR-023 section 6, merged in PR #418**: deciding its own
migration posture for existing content, it lands on "**Replace by default**, given the low volume and the fact
that it is test content; repair only where a specific story is expensive to reproduce"
(`adr-023-story-personalization-slots.md:327-328`). That is the same reasoning from the same premises, reached
independently. Two honest bounds on how much weight it carries: ADR-023 is `status: proposed` pending counsel
sign-off, not accepted, and its ruling is scoped to migrating content onto sentinels rather than to keep-or-retire
generally. So it corroborates the principle; it does not ratify it. The principle still rests on the owner
instruction. It has three consequences:

- **A9** takes the fix-or-replace path. A same-series exemption from the in-cell clone rule is **off the table**:
  two books of one series sharing an isomorphic tree is substandard regardless of the narrative continuity that
  explains it.
- **A8 gains teeth.** The audit may require replacement rather than negotiate an exemption.
  **Threshold decision closed 2026-07-26, on measurement: use `TAU_CELL` = 0.05, blocking, and do not pursue a
  `TAU_STRUCT` gate.** All 67 in-cell hand-authored pairs across the 18 populated cells were measured with
  `structural_distance`. At `TAU_CELL` exactly **one** pair fails, the known clone pair at 0.00095, with the
  next-lowest at 0.09123 and a median of 0.3956. So `TAU_CELL` flags precisely what A9 already intends to fix and
  nothing else, which means A8 can land blocking immediately with no calibration risk. A `TAU_STRUCT` (0.332507)
  gate is rejected on two independent grounds: it would fail **17 of 67 pairs (25%) across 12 of 18 cells**, which is
  the whole-class-failure anti-pattern PR #416's AL-051 warns against, and ADR-020's floor-recalibration
  amendment already made `TAU_STRUCT` **documentation only** ("No longer gates mutants; the anti-clone guarantee
  is `TAU_CELL` against parent + siblings"), so gating on it would contradict a ratified amendment. Note the
  baseline's own `clamps` entry already records the 0.000947 pair as the observed same-cell minimum that
  `TAU_CELL` is set to reject, so A8 is implementing an intent the baseline states rather than choosing a new bar.
  One scope note: `TAU_CELL` currently gates generated **mutants**; A8's delta is extending it to hand-authored
  in-cell pairs.
- **A10** leans to authoring the missing teen `short` skeletons rather than degrading the surface, since a cell
  that 422s is itself substandard. Still needs a call on sequencing, because this is content authoring with
  nothing to fix.

**Resolved (owner, 2026-07-25): difficulty.** Adopt A13 with a **3-hop** bound, re-evaluated as stories are
developed, rather than a fail-depth floor. And a new rule: **no decision may offer only fatal options; at least
one must allow advancing or looping back.** That becomes A14 (`L2-14`, see section 6.2 for why Layer 2).

**Resolved (owner, 2026-07-25): ring-2 attribution.** Sharing the child's first name with a connected family is
fine, because both guardians have agreed. Keep `display_name` as the attribution; B6 closes as
working-as-intended. The basis is recorded here so it is not re-raised: mutual connection consent is the
control, `coppa-compliance-audit.md:129` establishes that `display_name` is a first name or nickname and the
only stored child name, and the disclosure is inventoried in `gdpr-compliance-review.md:160`. ADR-016 should
gain a sentence stating ring-2 attribution granularity, since it currently defines the rings but not this.

**Resolved (owner, 2026-07-25): A14's scope.** The intent is that a reader is never shown option A and option B
where both result in death. Confirmed at the negative-valence reading below, which is a superset of that concern.

### 6.1 Child-reader review (2026-07-25)

A subagent evaluated A11, A13, A14 and the disposition principle purely from the reader's side, grounded in the
shipped reader UI and the ADR-011 band tables. It found the rules mostly right and the **wording** mostly not the
child's. Eight findings argued a rule was wrong; seven argued it needed different presentation. The substantive
ones are folded into A11, A13a/A13b, A14, and A15 through A18 above. Three worth keeping visible:

- **Band spread.** A13 and A14 both key on `death`/`capture`, which `_PROFILES` forbids at 3-5 and 5-8 and
  partially at 8-11. So the two youngest bands get **zero benefit** from either while carrying A13's downside if
  the multi-hop had been bound to the in-story button. A11 is where those bands live or die.
- **A coupling to watch.** A13 and A14 both make the world safer, and landing both unscoped at 13-16/16+ is the
  fastest route to a teen concluding the book cannot hurt them. Band-scoping A14 (above) is what prevents that.
- **The actionability test for any kid-facing restriction**: if a child cannot act on it, it is anxiety, not
  information. That is why the unnameable forbidden-theme warning is dropped rather than reworded.

### 6.2 How A14's scope was chosen, and why it is a Layer 2 rule

The rule reads naturally as three different tests, and the measurement separates them:

| Reading of "only fatal options" | Violations of 2,668 decisions | Assessment |
| --- | --- | --- |
| Every option is a `death`/`capture` terminal | **1** | The clear floor. Too narrow to be the whole rule. |
| Every option is a **negative-valence** terminal (doomed whatever you pick) | **37** | **Recommended.** Matches the intent: the reader is offered a decision with no good outcome. |
| Every option terminates at all | 144 | **Not implementable as stated.** These sit at median 90% of max tree depth and 88 of them offer a positive ending: they are climaxes. Forbidding them would make it impossible to end a story on a choice. |

The middle reading is adopted. The literal phrase "advancing or loop back" points at the third, which the
climax measurement rules out: a story must be able to end on a choice.

**Two findings from checking the gated case**, which the declared-choice count would have missed:

- ~~**No skeleton has "unconditional options all fatal with the survivable one gated."**~~ **Refuted 2026-07-26
  by the implementation.** `the-serpent-vaults` node `c22_gate` degrades exactly that way: its survivable option
  `c22_pass` is **conditional**, and the other four options each corridor into a `death` ending, so whenever that
  condition is false the reader is shown four options and dies on all of them. The original claim came from
  scanning direct terminals only, which cannot see a corridor. This does not weaken the argument for stating the
  rule over configurations, it strengthens it: the loophole 6.2 called theoretical is occupied.
- **18 decision nodes have every choice conditional** (in `the-cinder-bazaar`, `the-quiet-harbor-protocol`,
  `the-iron-spire-trial`, `the-glass-comet`, and the brass-lantern pair). That shape is already covered:
  **`L2-9`** blocks "any reachable non-ending configuration with zero visible choices", so a reader can never
  face an empty decision, and these skeletons pass the gate today.

Together those two are why A14 belongs in Layer 2 and must be written over visible choices. Nothing violates it
through gating today, and stating it that way costs nothing while closing the loophole permanently. `L2-9` and
`L2-11` already walk the same configuration space, so the `L2-12` cap is not a new constraint.

## 7. Method rules for this document

Carried from the errata, because the previous plans failed on all six.

1. Measurement and inference are separated. Section 1 is measurement; section 2 states what is not claimed.
2. Any invented proxy is declared as invented, with its free parameters and a sensitivity sweep, or it decides
   nothing.
3. One metric, one definition per table.
4. A later section may not quietly erase an earlier section's evidence. If it does, the earlier section is
   edited, not left standing.
5. Rule IDs, ADR numbers, and "this is unaddressed" claims are checked against `validator-rules.md` and the
   98-document corpus before being written. **Amended 2026-07-26**: checking `main` is not sufficient. A rule ID is
   free only if no *open* PR has claimed it. B3's `SR-8` was correct against `main` and wrong against PR #416.
   Check `main` and the open PR set, and say which basis the claim rests on.
6. Source text is quoted verbatim with its file path, or not quoted.
7. **Added 2026-07-26**: an ADR's status is quoted with its citation. A `proposed` ADR corroborates; it does not
   ratify. This document overclaimed ADR-023 as ratifying the disposition principle before checking its front
   matter.
8. **Added 2026-07-26**: editing a file under `skeletons/` is never a one-file change. Committed derived artifacts
   (`docs/architecture/diagrams/skeletons/<band>/<slug>.puml` and `.svg`, plus the
   `docs/architecture/story-skeletons.md` catalog) are regenerated by
   `scripts/render_skeleton_diagrams.py` and gated by
   `tests/integration/test_skeleton_diagrams_fresh.py`. Two commits in this workstream (the L2-14 content fixes and
   the first A20 slice) shipped with stale `.puml`, caught only by a full-suite run. Every remaining A20 skeleton
   will hit this, so regenerate and stage the derived files in the same commit. Note that the freshness gate checks
   `.puml` only: the `.svg` files, which are what `story-skeletons.md` actually links, are ungated and need
   `graphviz` installed locally, so a machine without `dot` silently renders 61 *empty* SVGs and reports success.
   Verify a re-render kept its node groups (`grep -c 'g id='`) before staging any SVG.
   **Amended 2026-07-26**: the diagrams are not the only catalog-derived artifact.
   `docs/planning/ws5_floor_baseline.json` is computed from the whole catalog by
   `scripts/calibrate_mutation_floors.py` and gated by
   `tests/unit/test_skeleton_mutation_floors.py`, so a one-line skeleton edit can make it stale too: adding a single
   effect to `the-sunken-temple` moved the observed same-cell minimum 0.000947 -> 0.000469 and shifted two
   state-space statistics. Regenerate it in the same commit, and **diff it rather than trusting it**: confirm the
   three thresholds (`TAU_STRUCT`, `TAU_CELL`, `TAU_STATE`) are unchanged and only observed statistics moved, since
   a threshold shift would silently re-baseline the gates that load this file. The general rule: after touching
   `skeletons/`, run the full suite before claiming done. Both stale-artifact failures in this workstream were found
   by a full run and by nothing else.

## 8. Reconciliation with PR #418 (merged) and PR #416 (open)

Review dated 2026-07-26, after merging `origin/main` at `bbf6ddb` (which contains PR #418,
"opt-in story personalization P1+P2 with fail-closed sentinel integrity (ADR-023)", and the v0.36.0 release
commit) into this branch. No conflicts.

**The plan's foundations survive intact.** PR #418 touched none of `skeletons/`, `diversity/`,
`generation/skeleton_match.py`, `fill.md`, `validator/{policy,series,band_profile}.py`,
`storybook/models.py`, `frontend/src/player/engine.ts`, `frontend/src/reader/Reader.tsx`, or `api/reading.py`.
Every measurement in section 1 was re-derived on the merged tree and is unchanged: 61 skeletons / 58
production-eligible, cell sizes `{3: 15, 4: 2, 5: 1}`, the clone pair at `structural_distance` 0.00095 with
unequal fingerprints, 2,668 decision nodes, and the echo floor at 132 themes / 129 passing at band `3-5` with the
same three withheld.

**What changed, and where it landed:**

| Change | Effect on this plan |
| --- | --- |
| ADR-023 section 4 replaces the Route A hero-name copy | **A11 rewritten.** Adopt ADR-023's wording; the child-reader review's proposal to reuse "Heroes in our stories always have made-up names" is withdrawn, because that is the sentence being replaced. |
| ADR-023 Ask 2 (shuffle semantics) | **Answered in A11**: display-only among generic names, no stored or generated effect, so it stays orthogonal to the sentinel mechanism. |
| ADR-023 section 3 sets a stricter ring-2 bar than B6 | **B6 re-scoped** from "add a sentence to ADR-016" to "participate in the single reconciliation edit ADR-023 requires". |
| Sentinels now exist in `node.body`, and the ATG never strips them | **New deliverable A19.** The only genuinely new defect this review found. |
| ADR-023 catalog facts (45 of 61 contracts, `HERO` in 39 of 45; pronouns hardcoded in beats) | **Added to section 1.** The pronoun examples independently corroborate the frozen-beat constraint that bounds the deferred alternate-phrasings item. |
| ADR-023 section 6 "Replace by default" | Corroborates the disposition principle in section 6, with the two bounds stated there. |
| Capability register at v1.8: **G18** and **K20** minted, K19 carries a copy dependency | **Noted in A11.** K19's row already records the rewording as a precondition on G18's flag and requires consistency with A11, so the two are already coupled in the register. |

**The rule-ID note.** On `main` today the maxima are `SR-7`, `L2-13`, `PL-22` (enumerated from
`src/cyo_adventure/validator/`). ADR-023 flags an `SR-8` collision and attributes it to PR #416, not #418; that
attribution is correct, and the apparent contradiction with this plan's "`SR-7` is the current maximum" is that
the two claims have different bases. Both are true. Open PR #416 claims `SR-8`, `PL-23` and `PL-24`. Its
"adds L2-13" is a catalog entry for a rule already shipped in `layer2.py`, not a new ID, so `L2-14` stays free
for A14. Net: B3 becomes `SR-9`, the deferred fail-depth floor becomes `PL-25`, A14 keeps `L2-14`, and all three
should be re-checked against #416's branch immediately before implementation rather than trusted from here.

### 8.1 Personalization is a diversity lever, and this review initially missed it

**Owner observation, 2026-07-26: the render-time substitution PR #418 adds should increase perceived diversity by
letting a reader insert themselves into an existing story.** That is correct, and the first pass of this review
treated #418 only as a coordination and contamination surface. Recorded here with the measurement, because the
measurement both confirms the point and says how to sequence it.

**Why it is a real lever, and a kind this plan did not have.** The original goal was *perceived* diversity. Every
Track A item works on **between-book distance**: theme signatures, structural distance, variation axes, clone
audits. Personalization works on a different axis, the **reader's relationship to a single book**, which nothing
else here touches. It is also the only lever that raises perceived novelty **without authoring a tree**, so it
acts immediately inside the binding constraint this plan keeps running into: 58 production-eligible skeletons, 15
of 18 non-empty cells holding exactly three, and P(a reader's second story reuses the first's tree) = 1/5.
ADR-023 row 1 calls the protagonist first name "the single detail that makes a book feel like the child's own",
and rows 2 through 8 compound on it.

**The trade is more favourable than it first appears.** The worry worth checking was that personalization
*removes* between-book variation: a made-up hero name differs per book, whereas a reader's own name is constant
across every book they read. That is directionally true and turns out to be small, because **`HERO` is the least
varied slot in the catalog**: 28 distinct values across 39 books (0.72), with `Wren` reused five times. Every
non-personalizable differentiator measured is at or near fully distinct (`THRESHOLD` 34/34, `ENTRANCE` 24/24,
`DEADLINE` 19/19, `GOAL` 17/17, all `ROUTE_*_CHAR` 1.00). So opting in spends the catalog's **weakest**
differentiating axis and leaves the strong ones intact. One exception to sequence deliberately: **`COMPANION` is
14/14 fully distinct** and is personalizable under ADR-023 row 3, so a sibling substitution there does spend a
maximally differentiating axis. Prefer `HERO` first; treat `COMPANION` as a knowing trade, not a free one.

**The honest limit.** Personalization raises the floor on how engaging any one book feels. It does not raise the
ceiling on how *distinguishable* two books are: the same tree with your name in it is still the same tree, so
the 1/5 reuse probability and the isomorphic pair are untouched. It is additive to the structural work, not a
substitute for it, and it makes the surviving structural differentiators carry proportionally more of the load,
which is an argument for keeping A8 and A9 at priority rather than relaxing them.

**The actionable finding: eligibility is anti-correlated with need.** Contract coverage runs 100% at `5-8` and
`8-11` but 57% at `13-16` and 64% at `16+` and `10-13`, with 15 of 16 gaps at `10-13` or above. The teen bands
have the thinnest catalog by every measure in section 1, and both books of the isomorphic clone pair have no
contract at all, so the two books that most need differentiation help get **none** from this mechanism. That is
cheap to fix relative to authoring trees, and it becomes **A20**.

**Two standing obligations inherited from #416, which will bind this work once it merges:**

1. Its new `CLAUDE.md` "Authoring Lessons Requirement" directive mandates appending to
   `docs/planning/authoring-lessons-log.md`, validated by `scripts/check_lessons_log.py`, for any authoring or
   validator work. A8, A14, A19 and B3 are all validator work by that definition.
2. Its AL-014/AL-044 report that the anti-clone floor is unreachable for hand-authored shells, with two withheld
   books at structural distance 0.0139 against a 0.05 floor. That is **independent corroboration of A8's finding
   from a different corpus**, and it sharpens the section 6 threshold decision: the failing set is larger than the
   one clone pair this plan measured, so measure it across both corpora before picking `TAU_CELL` or `TAU_STRUCT`.
