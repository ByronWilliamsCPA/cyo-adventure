---
schema_type: planning
title: "Story Structure Diversity: Critical Analysis of the Structural Ceiling"
description: "A root-cause analysis of why the skeleton model produced a few base structures that swap
  themes and read alike, despite the CYOA structure research and a substantial diversity workstream.
  Locates the ceiling in five compounding causes and proposes a prioritized path that shifts effort
  from graph-level metrics to experience-level variation."
tags:
  - planning
  - generation
  - diversity
  - storybook
status: active
owner: core-maintainer
authors:
  - name: "Claude (analysis session, branch claude/story-structure-diversity-ba8swy)"
purpose: "Answer the owner's question: how does the current node-structure model limit story diversity,
  and what should change to improve story quality? Synthesizes and extends story-diversity-analysis.md,
  story-diversity-plan-v2.md, the ADR-011 research reconciliation, and a fresh measurement pass over the
  61-skeleton catalog and the diversity/mutation code as of 2026-08-02."
component: Strategy
source: "Full read of skeletons/ (61 files), generation/skeleton_match.py, story_requests/authoring_plan.py,
  diversity/*, moderation/leaf_diversity.py, mutation/*, flywheel/*, validator/{layer1,layer2,policy,
  band_profile,topology}.py, ADR-011/019/020, story-diversity-analysis.md and its errata/plan-v2,
  cyoa-book-benchmark-comparison.md, pathfinder-structure-exploration.md, authoring-lessons-log.md,
  design-review-kid-appeal-2026-08-01.md, unscheduled-work-register.md (2026-08-02)."
---

# Story Structure Diversity: Critical Analysis of the Structural Ceiling

## 1. The question, and the verdict

The observed failure: instead of a wide variety of unique stories, the pipeline produced a few base
structures that swap in themes and read very similar, and the structure research the model was built on
did not translate into story-like flow.

The verdict of this analysis: **the observation is correct, it is now well documented internally, and
its root cause is not any single defect.** Five causes compound, and they sit at different layers:

1. The research-to-model translation flattened a narrative taxonomy into an enforcement grammar that
   can only distinguish three graph shapes, so "topology diversity" is partly nominal.
2. The validator's scale envelopes act as convergence targets, not just guardrails: every skeleton in a
   cell is pushed toward the same size, ending fraction, prose density, and spine length.
3. The catalog's provenance guaranteed a template feel: 18 cells seeded with one skeleton each (13 of
   the 18 seeds on a single topology), grown to 3 per cell in one automated wave, with zero
   mutation-derived or fresh-generated trees promoted since.
4. The beat armature is frozen: every fill of a skeleton renders the same scenes, in the same order,
   at the same word budgets, forever. Themes are paint on a fixed mural. This is the direct mechanism
   behind "swapped in themes and read very similar."
5. The diversity machinery that was supposed to compensate measures the wrong object (the graph, not
   the experience), and its enforcement teeth are advisory, fail-open, or inert on realistic input.

The July remediation ([story-diversity-plan-v2.md](story-diversity-plan-v2.md), deliverables A1-A8,
A14, A19, B1-B3, B5 delivered 2026-07-26) fixed the mechanical defects in cause 5. Causes 1-4 are
still fully in force. Section 5 proposes the path, ordered by what changes a reader's experience per
unit of effort.

Terminology note: "structure" below means three distinct things that the current tooling conflates,
and keeping them separate is half the argument:

- **Graph structure**: nodes, edges, endings. What `structural_distance` measures.
- **Experience structure**: what one read feels like, choice cadence, scene sequence, outcome mix,
  where agency lives on a path. Largely unmeasured.
- **Scene structure**: the beat text inside each node. Byte-frozen per skeleton.

## 2. Root causes

### 2.1 The research translated into budgets, not into flow

ADR-011 anchored the scale framework on external research (JHM 2019 plus a four-source
reconciliation), but two problems undermine the translation:

- **The research base is unrecoverable.** ADR-011 cites `docs/planning/research/`; that directory was
  never committed (noted in ADR-011's Related section and
  [design-review-kid-appeal-2026-08-01.md](design-review-kid-appeal-2026-08-01.md) section 6 item 5).
  The measurements exist only as numbers quoted in the ADR, the source is print-only and ages 9-12
  only, and at least one constant attributed to ADR-011 was later found to carry an invented citation
  (AL-076). The model's empirical foundation cannot be re-examined, only trusted or re-done.
- **What survived translation is the countable part.** Node budgets, ending fractions, words per node,
  and decisions per path became enforced tables (`validator/band_profile.py:159-178`,
  `validator/policy.py`). What did not survive is everything the research said about *why* those books
  worked: pacing, the placement of consequence, the feel of a decision mattering. The corpus itself
  drifted from the source on the one flow metric that was re-checked: the mean of per-skeleton maximum
  indegree is 7.79 against JHM's 1.5, with only 25 of 61 skeletons inside the source range (ADR-011
  section 7, 2026-07-27 clarification). Reconvergence targets remain an unreconciled research action
  (UW-G17, needs an ADR-011 amendment).

The consequence: the gate can prove a story is the right *size* for its band, and cannot say anything
about whether it *flows* like the books the research measured. "Story-like flow" was never encoded, so
the pipeline never optimized for it.

### 2.2 The envelopes are convergence targets

Each of the 18 production cells pins `(min_nodes, max_nodes, max_depth)` (PL-21 plus
`_PRODUCTION_CELLS`), PL-17 floors endings at a fixed fraction of nodes (15% prose, 25% gamebook),
PL-19 pins words per node, and PL-20 floors the shortest satisfying path. Individually each rule is
defensible. Jointly they define a narrow basin, and the catalog demonstrably sits at the bottom of it:

- Every measured node count lands inside its cell window; gamebooks hug the 25% ending floor from just
  above (27-33% across the board).
- Five of the six gauntlets carry the **identical** ending signature: exactly 2 positive and 1 neutral
  ending against 76-204 negative ones. PL-24's own calibration note records that every gamebook sits
  at 2.1-4.8% positive endings with no overlap against prose. Three trees per gamebook cell, all with
  a 95-98% negative-ending share, is why a teen reader experiences "another maze where I die"
  regardless of which tree is drawn ([story-diversity-analysis.md](story-diversity-analysis.md)
  section 2.4).
- AL-026 documents the perverse incentive directly: PL-17's breadth-scaled endings floor pushes
  authors toward terminating failure leaves, which halves the typical read (a 746-node book with a
  median read of 5 pages). The floor and read quality are in tension, and the floor is the blocking
  rule.

A floor that every artifact sits just above is not a floor; it is a spec. The envelopes were meant to
bound the space and instead they describe its center of mass.

### 2.3 Six topology names, three checkable shapes

PL-18 validates the declared topology via `admissible_topologies` (`validator/topology.py`), which can
only distinguish three equivalence classes: cyclic (`loop_and_grow` = `open_map`), acyclic without
reconvergence (`time_cave` = `sorting_hat`), and acyclic with reconvergence (`branch_and_bottleneck` =
`gauntlet`). The six Ashwell-derived labels are an authorial convention beyond that; 28 of 61 skeletons
sit in the third class, where the checker cannot tell a quest from a death maze. Ashwell's `quest` was
merged away and `floating_modules` deferred, so the shape vocabulary is narrower than the source
taxonomy to begin with.

This matters for diversity because the topology label is the main structural variety claim the catalog
makes ("every kid-band cell holds three different topologies"). That claim is real at the feature-vector
level, but the reader-facing differences within a class (a gauntlet's corridor pressure vs a
branch-and-bottleneck's route freedom) are carried entirely by authoring discipline that nothing
verifies, and the in-cell "different topologies" can be two labels from one equivalence class.

### 2.4 Provenance: one seed wave, one expansion wave, zero organic growth since

The catalog's history explains the "few base models" feel more economically than any metric:

- The initial inventory run seeded exactly one skeleton per cell, and 13 of those 18 seeds were
  `branch_and_bottleneck` ([story-inventory-initial-run.md](story-inventory-initial-run.md) section 2).
- Wave 5 grew each cell to 3 in a single automated design pass. 15 of 18 cells still hold exactly 3
  trees; a child's second story in a cell has a 1-in-5 chance of reusing the first's tree, and a child
  who reads four stories at one band and length must repeat a tree (arithmetic, not tuning).
- One "pair" of that variety is fake: `the-sunken-temple` and `the-harrowstone-keep` are
  graph-isomorphic (550 nodes, WL-hash equal), a deliberate series re-skin that ships allowlisted in
  the clone audit. Its cell nominally holds five trees and actually holds four.
- All 16 committed lineage records are `origin: fresh, hand-authored`. The entire ADR-020 mutation
  engine (five operator families, floors, acceptance stages, a promotion workflow) has promoted **zero
  skeletons** to date, and the WS-8 flywheel's trigger has been dark for most real requests until the
  A1/A2 vocabulary fixes landed (2026-07-26). The structure-growth machinery exists; it has simply
  never run in anger.

So the structure space is not merely constrained; it is static. Selection can only permute a small
fixed set, and the set was authored in two batches under the same envelopes by the same process, which
is exactly the recipe for a family resemblance.

### 2.5 The frozen beat armature is the "themes swapped in" mechanism

This is the deepest cause and the one no delivered workstream touches. Every node body is
`<<FILL role=R words=N beats='...'>>`; the beat text is byte-identical across every fill of that
skeleton forever; `fill.md` requires the prose to depict that exact beat; and the Stage 1 fidelity
gate blocks on it. The theme contract system (ADR-019) substitutes `{SLOT}` values inside the beats,
which is precisely a controlled noun swap. The result, as
[story-diversity-analysis.md](story-diversity-analysis.md) section 3.4 puts it: the slot values and
the prose change, the scene does not.

Push the fill prompt harder toward re-imagining and it collides with the fidelity gate; fidelity wins
because it is the blocking constraint. So the anti-template guard, even if it were calibrated and
blocking, measures prose distance between two renderings of the same storyboard. The ceiling on how
different two fills can feel is set by the armature, and with 3 trees per cell that ceiling is low and
is hit quickly by any regular reader. "Alternate beat phrasings" (beat variants sharing an outcome
contract) is ranked as the real ceiling-lifter in the prior analysis and currently sits blocked in
UW-G12 with no design doc.

## 3. Why the diversity machinery has not compensated

State as of 2026-08-02, after the July remediation:

**Fixed and real:** the similarity vocabulary now covers 99% of catalog themes (A1), containment
replaced the asymmetric Jaccard (A2), `tau_theme` was re-derived (A5), the saturation ladder can
escalate (A3), the escalation level and prior-fill context now reach the fill prompt (A6), a
deterministic variation axis is drawn per request (A7), the in-cell clone audit blocks in CI (A8), and
`L2-14` bans all-fatal decisions (A14).

**Still structurally weak, in order of consequence:**

1. **Nothing that measures "same experience" can block anything.** The anti-template guard is
   advisory, fail-open, compares against exactly one prior fill (the most recent same-tree fill), and
   runs on an empty per-band threshold table (`diversity/leaf.py`, `_BAND_THRESHOLDS = {}`; UW-G04).
   The aggregate perceived-similarity score and repeat-adventure rate never gate by design
   (`diversity/aggregate.py`). A templated fill cannot be stopped today, only flagged.
2. **Selection is slug-keyed and structure-blind.** `structure_features` computes topology, decision
   ratio, valence histogram, depth, and reconvergence, and selection consumes none of it; weighting
   keys on `skeleton_slug` recency and theme reuse only (`generation/skeleton_match.py`). Two
   near-identical trees under different slugs count as differentiation; identical 98%-negative outcome
   mixes in a row are invisible.
3. **Every signal is family-scoped, not reader-scoped.** No `profile_id` exists anywhere in
   `diversity/`; a 20-row shared window gives each child in a 3-child family roughly 7 stories of
   protection, and the ATG can compare a child's fill against a sibling's story they never read.
4. **The structural metric cannot see what a reader sees.** `structural_distance` is a weighted
   feature-vector distance; its histogram terms are aggregate and position-blind. ADR-020 itself
   records the accepted cost that a mutation chain could move the metric without moving perceived
   structure. The converse also holds and is worse: two graphs can be far apart on the metric while
   delivering the same experience (same decision cadence, same corridor pattern, same outcome mix),
   because per-path experience is not in the feature vector at all. `TAU_CELL = 0.05` is 5% of the
   metric's range; it is an anti-clone bar, not a distinctness bar.
5. **The one true clone check is not deployed as one.** `structure_fingerprint` is node-id sensitive
   (renamed clones hash differently); the isomorphism that confirmed the live clone pair was computed
   ad hoc in the analysis, not in CI. WL-hash equality would be cheap to add to the in-cell audit.

The honest summary: after remediation, the machinery reliably prevents *catalog-level graph
duplication* and reliably *asks the model to try harder* when a theme repeats. It still cannot detect,
let alone block, the actual failure the owner observed, which is experience-level sameness across
different slugs and different themes.

## 4. Why it also does not read as story-like flow

Diversity aside, three measured properties of the current structures work against narrative feel, and
they are all downstream of the envelope logic in section 2.2:

- **The format's promise is undelivered on most pages.** 69% of non-ending nodes catalog-wide have
  exactly one choice (52-61% in kid bands, 70% at 13-16); mean branching is ~1.5 everywhere. These are
  scene-splits produced by per-node word ceilings, and 0 of 61 skeletons comply with the new ADR-011
  section 10 choice grammar as authored
  ([design-review-kid-appeal-2026-08-01.md](design-review-kid-appeal-2026-08-01.md), decision D1).
  A reader taps "continue" far more often than they choose.
- **Corridor deaths without agency.** 776 single-choice nodes lead only to a death or capture
  terminal; 58 of the 73 shallowest foreclosing terminals are reached through single-choice corridors
  where backing up one step re-presents the same fatal page. A13b (the ending-screen "try a different
  way" affordance) is designed but not delivered.
- **Breadth made of failure leaves.** The scale rules reward endings-count breadth, so large gamebooks
  put growth into short terminating branches rather than reader-visible journey (AL-026: median read
  5 pages / 302 words in a 42,085-word book; AL-027: nothing constrains the *typical* path length,
  only the fastest satisfying one).

These are quality defects independent of diversity: fixing repetition without fixing flow yields more
varied stories that still read like mazes punctuated by page-turns.

## 5. What to do

Ordered by reader-perceived gain per unit of effort, and by dependency. Items cite the register row
where one exists; nothing here proposes relaxing the safety gate, and nothing needs to (the frozen
safety object is the ADR-011 constraint grammar, not the graphs).

### 5.1 Make the built machinery bite (small, this quarter)

1. **Calibrate the ATG per band and promote it to blocking** (UW-G04), comparing against the k most
   recent same-tree fills rather than one, with per-`profile_id` scoping where history allows. Until
   the one guard aimed at "themes swapped in" can fail a fill, everything else is advisory theater.
2. **Feature-aware selection weighting.** De-weight candidates by `structural_distance` and
   valence-histogram proximity to the reader's recent stories, alongside slug recency. The vector is
   already computed; the novelty floor form `1/(1+x)` preserves decision C-4. This makes the clone
   pair and the identical gamebook outcome mixes self-correcting at selection time.
3. **Add WL-hash isomorphism to the in-cell audit** so renamed clones are caught by construction, and
   **resolve A9 item 2** (restructure `the-sunken-temple`, UW-G03) so the allowlist returns to empty.
4. **Adopt AL-027's median-walk floor as an advisory** so typical-read length is finally a measured
   property, and revisit PL-17's endings floor for gamebook cells (its shape, not its existence): the
   floor should stop rewarding terminating-leaf breadth (AL-026's proposed change, still open).

### 5.2 Lift the armature ceiling (the decisive medium bet)

5. **Write the alternate-beats design doc and ADR now** (currently parked in UW-G12 behind "post
   launch" with no design). Two or three interchangeable beat variants per node sharing an outcome
   contract (same successor state, same choice semantics), selected per fill, with the fidelity gate
   checking against the issued variant. This is the only lever that changes what scene a reader gets
   on a repeated tree, it multiplies effective catalog size without new graphs (3 variants on a
   150-node tree is combinatorially a different book per fill), and its cost is authoring, which the
   A20 slotting program is already paying per skeleton anyway. Sequencing it with A20 (UW-G01) lets
   each skeleton be slotted and beat-varianted in one pass instead of two.
6. **Continue A20 as scheduled per-skeleton work** (14 skeletons, 4,305 nodes remaining) and close the
   catalog subject-tag gap found in plan v2 (9 of 22 subject tags, including the things children
   actually request, appear on zero stories), so similarity and personalization both have signal.

### 5.3 Measure the experience, not the graph (medium)

7. **Define 3-5 per-path experience metrics and put them in `structure_features`:** decision cadence
   (real choices per 100 words on a sampled walk), corridor ratio, outcome-mix entropy over sampled
   reads, median-walk depth, agency density (share of decisions whose options reach different
   endings). These are cheap deterministic walks, they capture exactly the sameness readers feel that
   the current 11 features miss, and they give selection (item 2), the mutation floors, and any future
   composer a target that correlates with experience. The existing walker validated against
   `StoryEngine` in lockstep (plan v2's measurement pass) is the substrate.
8. **Apply the ADR-011 section 10 choice grammar to all new structures** (it is currently
   grandfathered off for the whole catalog) and enforce D11's replacement rule: a grandfathered
   skeleton is excluded from selection for a cell once one compliant skeleton exists there. This is
   the concrete "story-like flow" fix: fewer single-choice corridors, per-band choice cadence,
   flavor/consequential mix.

### 5.4 Grow the structure space for real (large, staged)

9. **Run the flywheel end to end once, this quarter, on one saturated cell.** The mutation engine,
   floors, acceptance stages, and promotion workflow all exist and have promoted nothing. One
   T1/T3-chain mutant taken from candidate to merged catalog PR retires the integration risk, produces
   the first non-hand-authored tree, and tells us whether `TAU_CELL`-level mutants are perceptibly
   different (which item 7's metrics can then quantify). Follow with Wave-5-style expansion (UW-G13)
   targeting the cells the saturation signal actually flags, now that the signal works.
10. **Decide the pathfinder Phase 0 go/no-go** for the teen gamebook cells
    ([pathfinder-structure-exploration.md](pathfinder-structure-exploration.md)). The
    state/consequence axis is the least-used diversity axis (14 of 61 skeletons declare any variable),
    and it is the axis that changes "how it plays" rather than "what it is about." The build-as-roll
    doctrine is fully worked out, gate-compatible, and waiting on an owner decision plus legal review.
11. **Vary the outcome economy within gamebook cells deliberately.** ADR-011 sanctions "few wins, many
    fails" but never fixed a number; give each gamebook cell an authored spread (e.g. one tree at 2
    wins, one at 5-6 with graded setbacks, one survival-shaped with capture-dominant fails) so the
    fail-kind mix, the one variable plan v2 found actually keys satisfying-path mass (eta-squared
    0.636), differs between the trees a reader alternates across.

### 5.5 Re-anchor the research (process, cheap, overdue)

12. **Commit the research base or redo it** (UW-G17; the missing `docs/planning/research/` directory).
    The dispatched external pass on digital choice pacing for children (2026-08-01) should land as
    committed, citable notes, and the five reconciliation actions (exposure ratio, per-band fail
    states, reconvergence targets, an independent readability gate, edition anchoring) need the
    ADR-011 amendment the register already calls for. Until then, every structural constant is
    folklore with a table, and AL-076 showed at least one constant was retro-fitted to a citation.

## 6. What not to do

- **Do not add more trees under the current process as the primary fix.** More skeletons authored in
  batch under the same envelopes deepens the family resemblance (section 2.4) while multiplying the
  A20/beat-variant authoring debt per tree. Grow the catalog on demand (saturation-triggered), after
  items 5 and 7 exist to make new trees perceptibly different.
- **Do not relax the safety or determinism architecture for diversity.** Every lever above operates
  inside the ADR-011 grammar and the deterministic replay model. The benchmark comparison's permanent
  ceilings (no randomness, no unreachable content, variables capped near five by the L2-12 walk) have
  worked answers that stay inside the gate; none of the observed sameness is attributable to them.
- **Do not treat raised sampling temperature as a diversity lever.** It trades against the
  reading-level gate; the authored variation axes (A7) vary the dimension of variation instead of the
  noise level, and the outstanding work there is the empirical RL-13 check on real fills, not more
  noise.
- **Do not trust graph-level metrics as proxies for reader experience** when making promotion or
  selection decisions, until item 7 lands. `TAU_CELL` clearance is necessary, not sufficient; the
  human reviewer looking at the diagram is currently the only experience-level check in the promotion
  path, and ADR-020 says so.

## 7. Relationship to prior documents

This analysis agrees with, and does not re-derive, the measurements in
[story-diversity-analysis.md](story-diversity-analysis.md) (as corrected by
[story-diversity-review-errata.md](story-diversity-review-errata.md)) and the fact base in
[story-diversity-plan-v2.md](story-diversity-plan-v2.md). What it adds: the research-translation and
provenance root causes (sections 2.1, 2.4), the three-way split of graph vs experience vs scene
structure and the observation that all shipped metrics live at the graph layer (sections 1, 3, 5.3),
the floors-as-targets reading of the envelope system and its quality cost (sections 2.2, 4), and the
re-prioritization that puts beat variants and experience metrics ahead of catalog growth (section 5).
Open items already registered are cited by their UW rows rather than duplicated.
