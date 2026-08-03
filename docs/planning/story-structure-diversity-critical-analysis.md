---
schema_type: planning
title: "Story Structure Diversity: Critical Analysis of the Structural Ceiling"
description: "A root-cause analysis of why the skeleton model produced a few base structures that swap
  themes and read alike. Locates the ceiling in seven compounding causes joined by a feedback loop, and
  proposes a re-sequenced path that starts with deployment reality and authoring-path parity, then
  shifts effort from graph-level metrics to experience-level variation."
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
  band_profile,topology}.py, ADR-011/019/020/026, story-diversity-analysis.md and its errata/plan-v2,
  cyoa-book-benchmark-comparison.md, pathfinder-structure-exploration.md, authoring-lessons-log.md,
  design-review-kid-appeal-2026-08-01.md, unscheduled-work-register.md (2026-08-02)."
---

> **Adversarially reviewed (2026-08-02), same day, three independent passes.** One reviewer re-derived
> every claim against code and catalog (all headline measurements reproduced exactly: 7.79 mean max
> indegree, 28/61, 69%, 15/18 cells, 14/61 stateful); two more hunted for missing causes and
> interaction effects. Corrections are applied in place below. The material ones: **(a)** the original
> section 4 was stale on the day of writing against PR #532 / ADR-026 (rendered-stop flow), which
> already fixes the tap-through experience at bands 8-11+; **(b)** the gauntlet ending-signature
> paragraph had two numeric errors (four of six, not five; and a negative-vs-non-positive category
> conflation); **(c)** the clone pair is already excluded from ordinary selection as a series
> continuation, so selection-level fixes cannot "self-correct" it; **(d)** two additional major causes
> were found (deployment reachability, section 2.6; single-voice authoring paths, section 2.7); and
> **(e)** the causes interact as a feedback loop (section 5), which re-sequences the recommendations
> (section 6). The research-base rebuild recommended here has been executed on this branch: see
> [research/](research/README.md).
>
> **Corrected (2026-08-03).** Section 1's cause #6 and section 2.6's first bullet asserted that the 23
> authored catalog books (25 counting the 2 pilot re-themes) "were never imported"; that mechanism
> claim was wrong and is corrected in place below. Issue #347 records an import run against production
> on 2026-07-21 (the ADR-021 production catalog seed, 25 stories landed at `in_review`). The
> reachability finding itself is unchanged and still stands: `generation/import_catalog.py` never
> publishes by design, and nothing on record shows the separate admin promotion step,
> `publishing/catalog_publish.py::promote_catalog_story`, has ever run for this inventory, so a child
> can still reach zero catalog books today. This document has no database access and cannot confirm
> current database state; it can confirm only that an import run happened and that promotion, not
> import, is the outstanding step. Verifying live state is left as a runbook step in
> [story-structure-implementation-briefs.md](story-structure-implementation-briefs.md) (SQ-01).

# Story Structure Diversity: Critical Analysis of the Structural Ceiling

## 1. The question, and the verdict

The observed failure: instead of a wide variety of unique stories, the pipeline produced a few base
structures that swap in themes and read very similar, and the structure research the model was built on
did not translate into story-like flow.

The verdict: **the observation is correct, and its root cause is not any single defect.** Seven causes
compound, at different layers, and they are joined by a feedback loop that makes per-cause fixes
under-deliver:

1. The research-to-model translation kept the countable part (budgets) and lost the part about flow,
   and the research base itself is unrecoverable (section 2.1; rebuilt on this branch, see
   [research/](research/README.md)).
2. The validator's scale envelopes act as convergence targets, not just guardrails (section 2.2).
3. The topology vocabulary is enforceable only down to three realistic graph shapes, so declared
   variety is partly nominal (section 2.3).
4. The catalog is static and batch-authored: two waves, zero organic growth since (section 2.4).
5. The beat armature is frozen: every fill of a skeleton renders the same scenes forever; themes are
   paint on a fixed mural (section 2.5). This is the direct mechanism behind "swapped in themes."
6. What a child can actually reach today is a tiny, small-tree subset of the catalog, and can be zero:
   the authored inventory was imported to `in_review` (issue #347 records a production run on
   2026-07-21) but nothing has promoted it to `visibility='catalog'`, and the automated fill cannot
   render a large, method-dependent fraction of the skeletons, including every large gamebook
   (section 2.6).
7. The entire served-or-committed inventory was produced by authoring paths that bypass every
   diversity lever the July workstream built, by a single author-reviewer using one model per band
   (section 2.7).

The diversity machinery meant to compensate measures the graph rather than the experience, and its
teeth are advisory or inert (section 4). The causes then feed each other (section 5): family-scoped
signals keep the growth trigger dark exactly where demand exists, selection flattens to uniform
rotation over three trees while a theme-match bonus concentrates cross-family, the fidelity contract
compresses differentiation back to noun swaps, and the health metrics report success throughout.

Terminology used throughout, because the tooling conflates three things called "structure":

- **Graph structure**: nodes, edges, endings. What `structural_distance` measures.
- **Experience structure**: what one read feels like; choice cadence, scene sequence, outcome mix,
  where agency lives on a path. Largely unmeasured.
- **Scene structure**: the beat text inside each node. Byte-frozen per skeleton.

## 2. Root causes

### 2.1 The research translated into budgets, not into flow

ADR-011 anchored the scale framework on external research (JHM 2019 plus a four-source
reconciliation), but two problems undermine the translation:

- **The research base was unrecoverable, and the loss was structural.** ADR-011 cites
  `docs/planning/research/`; that directory sat in `.gitignore` under "Local research scratch docs
  (not source-controlled)", so the ADR cited a directory the repo was configured to never track, and
  no PR review could catch notes that could not be in a PR (ADR-011's own stale-citation note;
  [design-review-kid-appeal-2026-08-01.md](design-review-kid-appeal-2026-08-01.md) section 6 item 5;
  the ignore rule is removed on this branch).
  The high-confidence anchor (JHM 2019) is print-only and ages 9-12; 5-8 node counts are measured at
  medium confidence, 13-16 rests on gamebook metadata, and 3-5/16+ are product-defined. At least one
  constant attributed to ADR-011 was later found to carry an invented citation (AL-076). The
  foundation could not be re-examined, only trusted or re-done. **It has now been re-done**: this
  branch commits a rebuilt, citable research base under [research/](research/README.md). The rebuild traced
  "JHM 2019" to a real, open-access paper (Adams, Beckelhymer and Marr, *Journal of Humanistic
  Mathematics* 9(2), 2019, DOI 10.5642/jhummath.201902.05) and verified all four quoted constants
  against it: the endings median holds exactly, the page-node range and max-indegree figure are
  supported as fair glosses, and "~5 decisions/playthrough" is derived rather than stated by the
  paper. Two other constants (words/node ~100-150, total words ~8-15k) remain unverifiable from any
  indexed source and stay designer priors.
- **What survived translation is the countable part.** Node budgets, ending fractions, words per node,
  and decisions per path became enforced tables (`validator/band_profile.py:159-178` for the node
  budgets and `:358` for the breadth-scaled ending floors,
  `validator/policy.py`). What did not survive is everything the research said about *why* those books
  worked: pacing, placement of consequence, the feel of a decision mattering. The corpus drifted from
  the source on the one flow metric that was re-checked: mean per-skeleton maximum indegree is 7.79
  against JHM's 1.5, with only 25 of 61 skeletons inside the source range (ADR-011 section 7,
  2026-07-27 clarification; the corpus stays tree-like on average at mean indegree 1.17).
  Reconvergence targets remain an unreconciled research action (UW-G17, needs an ADR-011 amendment).

The consequence: the gate can prove a story is the right *size* for its band, and cannot say anything
about whether it *flows* like the books the research measured. The rebuilt research base confirms a
second-order problem: the literature itself is silent on choice cadence, tap pacing, and words-per-node
norms for children (see [research/choice-agency-pacing-and-failure.md](research/choice-agency-pacing-and-failure.md)
section 7), so several ADR-011 constants can never be research-anchored and must be labeled as
designer priors calibrated by our own telemetry.

### 2.2 The envelopes are convergence targets

Each of the 18 production cells pins `(min_nodes, max_nodes, max_depth)` (PL-21 plus
`_PRODUCTION_CELLS`), PL-17 floors endings at a fixed fraction of nodes (15% prose, 25% gamebook,
enforced as a floor with the node-count minimum a warning), PL-19 pins words per node, and PL-20
floors the shortest satisfying path. Individually each rule is defensible. Jointly they define a
narrow basin, and the catalog sits at the bottom of it:

- Every measured node count lands inside its cell window; gamebooks hug the 25% ending floor from just
  above (27.6-33.4% across all fourteen).
- Four of the six gauntlets carry the identical ending signature: exactly 2 positive and 1 neutral
  ending against 76-147 negative ones; a fifth differs only by two neutral endings (2/3/204). PL-24's
  calibration note records every committed gamebook fill at 2.1-4.8% positive endings with no overlap
  against prose (the current catalog spans 1.0-4.8%). Negative-*valence* share across the fourteen
  gamebooks runs 78.5-98.0%. Three trees per gamebook cell, all near-uniformly fail-heavy, is why a
  teen reader experiences "another maze where I die" regardless of which tree is drawn
  ([story-diversity-analysis.md](story-diversity-analysis.md) section 2.4).
- AL-026 documented the perverse incentive directly: PL-17's breadth-scaled endings floor pushes
  authors toward terminating failure leaves, which halved the typical read on the largest book (median
  5 pages of a 42,085-word book; since repaired to a 20-page median, AL-026 `applied`). The open
  remainder, revisiting the floor's shape so it stops rewarding terminating-leaf breadth, is tracked
  as UW-M06.

A floor that every artifact sits just above is not a floor; it is a spec. The envelopes were meant to
bound the space and instead they describe its center of mass.

### 2.3 Six topology names, about three checkable shapes

PL-18 validates the declared topology via `admissible_topologies` (`validator/topology.py:34-64`),
which emits four admissible sets: cyclic maps to {loop_and_grow, open_map}; an acyclic pure-linear
spine to {time_cave, gauntlet}; acyclic branching without reconvergence to {time_cave, sorting_hat};
acyclic with reconvergence to {branch_and_bottleneck, gauntlet}. No pure linear spine exists in the
catalog, so in practice three classes partition it: 17 cyclic, 16 acyclic-no-reconvergence, and 28 in
the {branch_and_bottleneck, gauntlet} class where the checker cannot tell a quest from a death maze.
Ashwell's `quest` was merged away and `floating_modules` deferred, so the shape vocabulary is narrower
than the source taxonomy to begin with (see
[research/cyoa-structure-measurements.md](research/cyoa-structure-measurements.md)).

This matters because the topology label is the main structural variety claim the catalog makes. The
reader-facing differences within a class are carried entirely by authoring discipline that nothing
verifies. And the claim is weaker than the catalog's own summary suggests: both 3-5 cells hold only
two distinct topology labels among their three trees (short: time_cave x2 + loop_and_grow; medium:
loop_and_grow x2 + time_cave).

### 2.4 Provenance: one seed wave, one expansion wave, zero organic growth since

The catalog's history explains the "few base models" feel more economically than any metric:

- The initial inventory run seeded exactly one skeleton per cell, and 13 of those 18 seeds were
  `branch_and_bottleneck` ([story-inventory-initial-run.md](story-inventory-initial-run.md) section 2).
- Wave 5 grew each cell to 3 in a single automated design pass. 15 of 18 cells still hold exactly 3
  trees; in the clean-state case a child's second story in a cell has a 1-in-5 chance of reusing the
  first's tree (section 5 shows the realistic steady state is worse), and a child who reads four
  stories at one band and length must repeat a tree.
- One nominal pair of that variety is a deliberate re-skin: `the-sunken-temple` and
  `the-harrowstone-keep` are graph-isomorphic (550 nodes, WL-hash equal), books 1 and 2 of the
  brass-lantern series. Because book 2 is excluded from ordinary cell selection as a continuation
  (`is_continuation_skeleton`, AL-045), the pair costs no ordinary-request variety today; it remains
  a catalog-integrity problem (A9 item 2, UW-G03) and a series-flow experience issue, not a selection
  one.
- All 16 committed lineage records are `origin: fresh, hand-authored`. The entire ADR-020 mutation
  engine has promoted **zero skeletons** to date, and the WS-8 flywheel trigger was dark for most real
  requests until the A1/A2 vocabulary fixes landed (2026-07-26). The structure-growth machinery
  exists; it has never run in anger.

So the structure space is not merely constrained; it is static. Selection can only permute a small
fixed set, authored in two batches under the same envelopes, which is the recipe for a family
resemblance.

### 2.5 The frozen beat armature is the "themes swapped in" mechanism

This is the deepest generation-side cause and the one no delivered workstream touches. Every node body
is `<<FILL role=R words=N beats='...'>>`; the beat text is byte-identical across every fill of that
skeleton forever; `fill.md` requires the prose to "depict this exact beat"; and the theme contract
system (ADR-019) substitutes `{SLOT}` values inside the beats, which is precisely a controlled noun
swap. The result, as [story-diversity-analysis.md](story-diversity-analysis.md) section 3.4 puts it:
the slot values and the prose change, the scene does not.

The enforcement mechanics are subtler than "a blocking gate," and worth stating precisely. The
beat-depiction check is the *soft* half of Stage 1: an LLM review judged by default by the same model
that wrote the fill, fail-open specifically on malformed responses (a non-string response or a JSON
decode failure; an uncaught transport error propagates), with a bounded repair budget (`max_repairs`,
default 3, shared between fidelity and structural repair) and then a downgrade to human review
rather than rejection (`generation/fidelity_gate.py`, `moderation/fidelity_review.py`,
`generation/worker.py`, `generation/orchestrator.py`). The hard-blocking Stage 1 checks (structure preserved, word-count tolerance)
do not measure beat depiction at all. What actually freezes the scene is the combination of the prompt
contract ("MUST depict this exact beat"), the flag-to-repair loop that rewrites flagged nodes without
the differentiation context (section 2.7), and the absence of any variant to render. Push the fill
toward re-imagining and the pipeline pushes it back probabilistically, not deterministically; the
equilibrium is the same either way. The ceiling on how different two fills can feel is set by the
armature, and with 3 trees per cell that ceiling is hit quickly by any regular reader. "Alternate beat
phrasings" (beat variants sharing an outcome contract) remains parked in UW-G12 with no design doc.

### 2.6 Reachability: the served space is a fraction of the analyzed space

Everything above analyzes the catalog and pipeline *as designed*. As deployed, two mechanisms shrink
what a child can actually receive far below the 61-skeleton catalog:

- **The authored inventory is unpublished, whatever its import state.** All 23 validator-passed filled
  books (plus 2 pilot re-themes; 25 total) were authored and are listed in
  [draft-stories-manifest.md](draft-stories-manifest.md) (UW-G14). Issue #347 records an import run
  against production on 2026-07-21 (the "ADR-021 production catalog seed", 25 stories landed at
  `in_review` via `generation/import_catalog.py`); whether those specific rows are still present and
  unmodified in a live database today is not something this document can confirm, only that a run
  happened. What holds regardless of that run's fate: `import_catalog.py` never publishes by design,
  and the only path to `visibility='catalog'` is the separate admin step,
  `publishing/catalog_publish.py::promote_catalog_story`. Nothing on record shows that step has run for
  this inventory. So the reachability gap is the same either way: an imported-but-unpromoted book sits
  at `in_review` under the `CATALOG_FAMILY_ID` sentinel, invisible to every kid profile, exactly as an
  unimported one would be. A child's library today contains only books generated on demand for their
  own family, plus whatever catalog titles, if any, an admin has separately promoted.
- **The automated fill can only render the small end of the catalog.** The fill is one completion of
  the whole Storybook capped at 32k output tokens (`generation/orchestrator.py`, `_MAX_TOKENS_PROSE`),
  with no chunking. The infeasible-skeleton count is method-dependent because it turns on the assumed
  words-to-tokens factor and per-node JSON overhead: plausible estimates put **between 16 and 29 of
  58 production-eligible skeletons over the cap** (1.3x factor with no overhead gives 16; 1.5x plus
  30 tokens/node gives 29), and the ground truth from actual fills is AL-046's "13 of the 26
  committed fills already exceed it". SQ-02's calibrated estimator settles the exact set; every
  method agrees the large gamebooks are out of reach.
  Selection has no feasibility predicate, so a large-cell request burns its repair budget and fails
  deterministically. The books that carry most of the catalog's structural range (long gamebooks,
  stateful books) cannot reach a child through the automated path at all.

The observed sameness was therefore generated almost entirely by a small, fill-feasible, single-voice
subset, and no amount of catalog-level diversity fixes that until the inventory ships and the fill can
render large trees. This is the largest single omission from the original version of this analysis.

### 2.7 Single-voice authoring paths that bypass the diversity machinery

Three compounding facts about how the existing content was actually made:

- **The manual skill path has none of the levers.** `.claude/skills/cyo-author/` carries no
  differentiation directive, no variation axis, and no anti-template interaction; its default with no
  brief is to fill the skeleton in its native theme, and its import path (`generation/import_story.py`)
  reads none of the differentiation metadata that `authoring_plan.py` persists. Every A6/A7 lever
  lives only in the automated worker. **All 23 draft books were written through the skill path**, so
  the first inventory a family would see was produced with zero anti-sameness machinery.
- **Model and prompt monoculture.** Per [story-inventory-initial-run.md](story-inventory-initial-run.md),
  one model authored all fills per band tier, one model designed all 36 Wave-5 skeletons in one pass,
  and every fill of every theme shares one static system block: the same drafting guide with a single
  second-person prose exemplar, and a guide that names `branch_and_bottleneck` as "the recommended
  structure pattern for all age bands" (`generation/templates/drafting_guide.md`). The fresh-generation
  prompt hard-instructs a reconverging branch-and-bottleneck shape for every Stage A
  (`generation/prompts.py`), so the only structure-growth prompt in the system can effectively author
  one shape.
- **Repair strips the context.** All three repair surfaces (structural, fidelity, moderation
  soft-gate) rebuild prompts without the theme brief, differentiation directive, variation axis, or
  drafting guide (`generation/prompts.py`, `generation/templates/fidelity_repair.md`,
  `moderation/repair.py`). The stories that needed extra passes, statistically the unusual ones, get
  rewritten by a model that no longer knows the craft instruction it was supposed to hold; the
  moderation repair's adopted output replaces the persisted blob with no human in the loop.
- Supporting uniformities on the same axis: intake gives every request the same protagonist scaffold,
  mid-envelope size target, `tier=1`, `structure_pattern=BRANCH_AND_BOTTLENECK`, and a
  keyword-matched tone that defaults to "gentle" (`story_requests/brief.py`, `story_requests/tone.py`);
  the A7 variation axis's recent-use exclusion parameter is unwired (the only call site passes no
  exclude list, and a re-run of a rejected fill reproduces the same axis on the same beats); and every
  cover is prompted into one fixed art style (`covers/prompt.py`), homogenizing the shelf itself.

One organizational fact spans all of this: one person is author, reviewer, adjudicator, promotion
gate, and (pre-launch) the entire test population. The family resemblance is structurally hardest to
see from inside that loop, and it was in fact detected by the owner reading outputs, not by any gate.

## 3. Why it also does not read as story-like flow

The graph-level facts hold: 69% of non-ending nodes catalog-wide have exactly one choice (5,873 of
8,573; 54-62% in kid bands, ~70% at 13-16), mean branching ~1.5 everywhere, and 776 single-choice
nodes lead only to a death or capture terminal. These are scene-splits produced by per-node word
ceilings, and they are why the *authored graphs* under-deliver the format's promise.

**Currency correction (2026-08-02):** PR #532 / ADR-026, which landed one commit before the first
version of this analysis, already changes what a reader experiences at bands 8-11 and up. The
rendered-stop flow (`player/stops.py`, `frontend/src/player/stops.ts`, wired in `Reader.tsx`) flows
consecutive single-choice nodes into one rendered stop, so every stop now ends at a real choice or an
ending, and `backOneStop` rewinds the whole flowed run, so a corridor death is one stop and Go back
exits the corridor. ADR-011 section 10 compliance is defined over rendered stops, not raw nodes, and
has not been measured; the "0 of 61 comply" figure circulating from the kid-appeal review is D1's
stricter node-level rule, not the ratified section 10 (the nodes-vs-stops unit confusion is exactly
AL-076's lesson).

What remains true and unaddressed after ADR-026:

- Bands 3-5 and 5-8 render discrete pages; the flow fix does not apply there, and those bands' pacing
  rides directly on the authored graph.
- The flow fix changes rendering, not authoring: flowed stops can be long, and the flavor/consequence
  mix and cadence of *real* decisions is still whatever the graph gives (the grammar that would govern
  it applies only to new skeletons, none of which exist yet).
- A13b (the ending-screen "try a different way" affordance) is designed, ADR-024-authorized, and not
  delivered.
- Breadth made of failure leaves remains an authoring-incentive problem (UW-M06), even after the
  largest book's shallow leaves were repaired.

Fixing repetition without fixing flow yields more varied stories that still read like mazes punctuated
by page-turns; ADR-026 removed the page-turns for older bands, and the rest stands.

## 4. Why the diversity machinery has not compensated

State as of 2026-08-02, after the July remediation (A1-A8, A14, A19, B1-B3, B5 delivered
2026-07-26; W2.2 theme-aware selection delivered in #532):

**Fixed and real:** the similarity vocabulary covers 99% of catalog themes (A1), containment replaced
the asymmetric Jaccard (A2), `tau_theme` re-derived (A5), the saturation ladder can escalate (A3), the
escalation level and prior-fill context reach the fill prompt (A6), a deterministic variation axis is
drawn per request (A7), the in-cell clone audit blocks in CI (A8), `L2-14` bans all-fatal decisions
(A14), and selection now takes a theme-overlap attraction multiplier (W2.2).

**Still structurally weak, in order of consequence:**

1. **Nothing that measures "same experience" can block anything.** The anti-template guard is
   advisory and fail-open *by supervisor-ruled contract* (`moderation/leaf_diversity.py`), compares
   against exactly one prior fill (the most recent same-tree fill), and its per-band threshold table
   is empty so every band runs on the uncalibrated defaults (`diversity/leaf.py`); it does emit
   PASS/WARN/FAIL today, but a FAIL produces soft flags, never a block. The aggregate
   perceived-similarity score and repeat-adventure rate never gate by design
   (`diversity/aggregate.py`). Promoting the guard to blocking is therefore a contract revision plus
   calibration, not a threshold fill-in.
2. **Selection is slug-keyed and structure-blind, and its one new theme term concentrates.** Selection
   consumes none of `structure_features` (topology, decision ratio, valence histogram, depth,
   reconvergence are computed and discarded); weighting keys on slug recency, theme reuse, and, since
   #532, a theme-overlap *attraction* bonus of up to 2x. Section 5 shows that bonus is a cross-family
   concentrator. Identical outcome mixes in a row are invisible to it.
3. **Every signal is family-scoped, not reader-scoped.** No `profile_id` exists anywhere in
   `diversity/`; a 20-row shared window (which counts every version row, including retries) gives each
   child in a 3-child family roughly 7 stories of protection, and the ATG can compare a child's fill
   against a sibling's story they never read.
4. **The structural metric cannot see what a reader sees.** `structural_distance` is a feature-vector
   distance; its histogram terms are aggregate and position-blind, and ADR-020 records as an accepted
   cost that a mutation chain could move the metric without moving perceived structure. The converse
   also holds: two graphs far apart on the metric can deliver the same experience (same decision
   cadence, same corridor pattern, same outcome mix), because per-path experience is not in the
   feature vector at all. `TAU_CELL = 0.05` is an anti-clone bar, not a distinctness bar.
5. **Clone detection works but is unlabeled.** A renamed exact clone has an identical feature vector,
   so the blocking A8 audit already catches it at distance ~0 (that is how the live pair was caught).
   What is missing is proof-of-isomorphism labeling (WL-hash equality) to distinguish "true clone"
   from "very close pair"; note WL hashes must be compared within-run, never against stored values,
   because networkx changed directed-graph hashing in v3.5.

The honest summary: the machinery reliably prevents catalog-level graph duplication and asks the model
to try harder when a theme repeats. It cannot detect, let alone block, experience-level sameness, and
several of its levers are dark on the paths that produced all existing content (section 2.7).

## 5. The compounding loop

The interaction review found that the causes above are not additive; they form a loop. The load-bearing
interactions:

- **The theme-overlap bonus concentrates cross-family.** Within one family the 2x attraction bonus is
  counterweighted by recency and theme-reuse penalties, but both counterweights are family-scoped and
  reset across families. For any family's *first* request on a popular theme in a 3-tree cell, the
  themed tree draws with probability ~1/2 instead of 1/3. The population-level modal outcome is the
  same (tree, theme) pair in every family, which is the maximal-similarity configuration (same-tree
  noun-adjacent fills score ~0.96 on the WS-0 perceived-similarity anchor). This becomes visible the
  moment ring-2 recommendation sharing ships: a friend's "their" dragon book is your dragon book with
  different names.
- **The realistic repeat rate is ~1/3 to 1/2, not 1/5.** The 1-in-5 figure is the clean-state
  second-story case. The inverse-frequency weight flattens to uniform once all three candidates carry
  equal counts (after ~3 stories in a cell), retries consume window slots (a re-run creates a new
  storybook and version row on the same slug), and sibling churn evicts entries on a 2-3 story cycle
  in a 3-child family. Steady state: every pick uniform over 3, pushed toward the themed tree by the
  bonus above.
- **The differentiation directive and the beat contract are opposed instructions.** At CATALOG
  escalation the prompt orders "change the setting wholesale... give the cast different wants" while
  the same prompt's fidelity contract orders the beat's events and outcome kept identical, and flagged
  nodes are rewritten by a context-stripped repair. The only output satisfying both masters is surface
  renaming, which is the definition of the failure being guarded against. Consequence: **promoting the
  ATG to blocking before beat variants exist creates an unsatisfiable constraint set** and yields
  retry loops, not diversity.
- **The growth sensor is dark exactly where demand exists.** CATALOG escalation requires every cell
  slug to carry a similar-theme story in the 20-row window; out-of-vocabulary themes produce empty
  signatures and containment 0 forever; multi-child window churn evicts the evidence before the
  threshold is met. So the two populations with the worst repeat experience (multi-child families,
  unusual-theme families) generate the least saturation signal, and the flywheel's "grow on demand"
  doctrine has a demand sensor anti-correlated with demand. Its distinct-requests threshold also
  counts request ids, not families, so one prolific household can commission growth alone.
- **The pool arithmetic runs on the nominal pool, not the feasible one.** With the 32k fill cap and no
  feasibility predicate (section 2.6), the automated-path pool in long cells is the fillable subset,
  possibly 1 or 0, and the practical workaround (admin slug override to a known-fillable tree)
  concentrates harder. Failed jobs write no version row, so this is invisible to the recency window.
- **The D11 replacement rule schedules a pool-of-1 trough.** As written, the first grammar-compliant
  skeleton in a cell excludes all grandfathered trees from selection there; at the flywheel's promotion
  caps (4 merges/month, 30-day per-cell cooldown) that cell then serves one tree for a month or more,
  and the transition across 18 cells is a year of rolling pool-of-1 cells. The rule needs a floor
  (exclude grandfathered trees only once at least 2 compliant trees exist per cell).
- **The health metrics reward the failure mode.** Effective catalog size is entropy over slugs, which
  the uniform-rotation steady state maximizes at exactly the moment experience is most repetitive; the
  flywheel's headline metric ("net new trees per month") counts TAU_CELL-clearing merges, so four
  metric-distinct, experience-identical trees per month reads as full-budget success; and the
  engagement-telemetry design (reader-path-engagement-design.md, status proposed, not yet built)
  keys per book, so as designed, "everyone stops at the same corridor" would never be attributed to
  the shared frozen beat that causes it in every fill of a tree.
- **Growth and deepening compete for one person's capacity.** A20 slotting (4,305 nodes remaining),
  beat variants, Wave 5 (36 skeletons), and every flywheel promotion all draw on the same single
  author-reviewer, and each merged tree adds ~300 nodes of slotting-plus-variant obligation. Growth
  makes deepening more expensive; the recommendations must share a capacity model, not compete
  silently.

## 6. What to do

> **Execution plan**: this section's program is scheduled, with deliverable IDs, dependencies,
> acceptance criteria, capacity model, and owner gates, in
> [story-structure-improvement-plan.md](story-structure-improvement-plan.md).

<!-- Rationale for the directive below: the item numbers deliberately continue 1..17 across the
     subsection boundaries, because later text cross-references specific plan items by number
     (see section 7). Keep the disable directive itself on ONE line: markdownlint ignores a
     directive comment that wraps, silently, with no warning. -->
<!-- markdownlint-disable MD029 -->

Re-sequenced after review. The ordering principle: first make the *deployed* system match the analyzed
one (6.0), then make the built machinery bite where it can (6.1), then lift the ceiling (6.2), then
measure what matters (6.3), then grow (6.4). Nothing here relaxes the safety gate; the frozen safety
object is the ADR-011 constraint grammar, not the graphs.

### 6.0 Close the deployment gap first (small, immediate, prerequisite to everything)

1. **Ship the inventory**: run the built import and publish flow for the 23 authored books (UW-G14).
   Until the catalog is reachable, every catalog-diversity lever is idle and the observed sameness is
   authoring-side by construction.
2. **Add a fill-feasibility predicate to selection** (AL-046): exclude or de-weight skeletons whose
   token demand exceeds the fill cap, and pursue the act-scoped fill loop, which is also the natural
   seam for intra-book voice variation. This corrects the pool arithmetic every other selection fix
   builds on.
3. **Close the skill-path parity gap**: thread the differentiation directive, variation axis, and (once
   it exists) ATG context into `.claude/skills/cyo-author/` and `generation/import_story.py`, so the
   path that produces inventory stops bypassing the machinery.
4. **Two one-line-scale fixes**: wire the `exclude=` parameter into `select_axis` (per-family recent
   axes) and seed it per job rather than per request so re-runs vary; thread the variation axis and
   differentiation context into all three repair prompts so repairs stop regressing to house style.
5. **Vary the cover-art style clause** by band and tone (`covers/prompt.py`): the shelf is the first
   place a reader judges variety, and today every book is prompted into one style.

### 6.1 Make the built machinery bite (small, this quarter)

6. **Calibrate the ATG per band and revise its contract toward blocking, sequenced AFTER beat variants
   exist** (UW-G04; the contract in `moderation/leaf_diversity.py` is supervisor-ruled fail-open, so
   this is a ruling change, not a config change). Compare against the k most recent same-tree fills,
   scoped per `profile_id` where history allows. Blocking it before variants exist creates the
   unsatisfiable constraint set of section 5.
7. **Rebalance selection**: cap or population-scope the theme-overlap attraction bonus (it currently
   concentrates cross-family); add de-weighting by `structural_distance` and valence-histogram
   proximity to the reader's recent stories (per-profile, falling back to family). The novelty floor
   form `1/(1+x)` is preserved. Count distinct storybooks rather than versions in the recency window.
8. **Label true clones**: add within-run WL-hash isomorphism to the in-cell audit (proof, not
   detection; the distance audit already catches clones), and resolve A9 item 2 (UW-G03) so the
   allowlist returns to empty.
9. **Adopt AL-027's median-walk floor as an advisory** and take up UW-M06 (reshape PL-17's gamebook
   floor so it stops rewarding terminating-leaf breadth).

### 6.2 Lift the armature ceiling (the decisive medium bet)

10. **Write the alternate-beats design doc and ADR now** (parked in UW-G12 with no design). Two or
    three interchangeable beat variants per node sharing an outcome contract (same successor state,
    same choice semantics), selected per fill, with the fidelity gate checking against the issued
    variant. This is the only lever that changes what scene a reader gets on a repeated tree, and it
    dissolves the directive-vs-fidelity contradiction, which makes it a *prerequisite* for item 6, not
    a parallel track. Two review-added requirements: variants must be authored under deliberately
    varied model/prompt/exemplar settings or they inherit the monoculture correlation (section 2.7),
    and the program needs an explicit capacity model shared with A20 and catalog growth (section 5).
    Sequence per skeleton with A20 (UW-G01) so each skeleton is slotted and beat-varianted in one pass.
11. **Continue A20 as scheduled per-skeleton work** and close the catalog subject-tag gap (9 of 22
    subject tags, including the things children actually request, appear on zero stories).

### 6.3 Measure the experience, not the graph (medium)

12. **Add per-path experience metrics to `structure_features`**: decision cadence over rendered stops
    (post-ADR-026, cadence must be measured on stops, not raw nodes), corridor ratio, outcome-mix
    entropy over sampled reads, median-walk depth, agency density (share of decisions whose options
    reach different endings). Cheap deterministic walks; they give selection, the mutation floors, and
    any future composer a target that correlates with what a reader feels. Add a skeleton-level rollup
    to engagement telemetry so per-node stop signals aggregate across fills of a tree.
13. **Measure ADR-011 section 10 compliance over rendered stops** (it has never been measured; the
    circulating "0 of 61" is the stricter node-level D1 rule), apply the grammar to all new
    structures, and amend D11 with a floor: grandfathered skeletons leave selection only when at
    least 2 compliant trees exist in the cell, avoiding the scheduled pool-of-1 trough. Deliver A13b.

### 6.4 Grow the structure space for real (large, staged)

14. **Run the flywheel end to end once, manually targeted** (the trigger will not have fired for the
    cells that need growth; respecify it to count distinct families, not request ids, and to treat
    unknown themes conservatively before trusting "grow on demand"). Note AL-049: mutation operators
    currently cannot handle the state-heavy ceiling-size gamebooks, which are exactly the most
    homogeneous cells; fix or scope that first.
15. **Decide the pathfinder Phase 0 go/no-go** for the teen gamebook cells
    ([pathfinder-structure-exploration.md](pathfinder-structure-exploration.md)). The
    state/consequence axis is the least-used diversity axis (14 of 61 skeletons declare any variable)
    and the one that changes "how it plays."
16. **Vary the outcome economy within gamebook cells deliberately** (e.g. one tree at 2 wins, one at
    5-6 with graded setbacks, one capture-dominant survival shape), so the fail-kind mix, the one
    variable that actually keys satisfying-path mass (eta-squared 0.636), differs between the trees a
    reader alternates across. Value rises further once gamification ships: an endings-gallery over a
    98%-negative cell is a wall of death cards.

### 6.5 Keep the research base honest (done on this branch, one action open)

17. The research base is rebuilt under [research/](research/README.md): structure taxonomy and published-book
    measurements, and the academic base for agency, pacing, reading rates, and fail states, each with
    graded sources and an explicit silence list. The open action is the ADR-011 amendment UW-G17
    already calls for: expand "JHM 2019" to its full verified citation (Adams, Beckelhymer and Marr
    2019, DOI 10.5642/jhummath.201902.05), mark the decisions-per-playthrough constant as derived,
    label the literature-silent constants (words/node, cadence, endings floors) as designer priors
    calibrated by telemetry, and record the Ashwell eight-pattern-to-six-topology mapping explicitly.

<!-- markdownlint-enable MD029 -->

## 7. What not to do

- **Do not add more trees under the current process as the primary fix.** Batch authoring under the
  same envelopes, prompts, and models deepens the family resemblance (sections 2.4, 2.7) while
  multiplying the slotting and variant debt per tree (section 5). Grow on demand, after the demand
  sensor is fixed and items 10/12 exist to make new trees perceptibly different.
- **Do not relax the safety or determinism architecture for diversity.** Every lever above operates
  inside the ADR-011 grammar and the deterministic replay model. The benchmark comparison's permanent
  ceilings (no randomness, no unreachable content, variables capped near five by the L2-12 walk) have
  worked answers that stay inside the gate; none of the observed sameness is attributable to them.
- **Do not treat raised sampling temperature as a diversity lever.** It trades against the
  reading-level gate; the authored variation axes vary the dimension of variation instead of the noise
  level. The outstanding work there is wiring (section 6.0 item 4) and the empirical RL-13 check on
  real fills, not more noise.
- **Do not trust graph-level metrics as proxies for reader experience** in promotion or selection
  decisions until item 12 lands, and do not trust the current dashboard as evidence of health: ECS and
  net-new-trees are maximized by the failure mode itself (section 5).

## 8. Relationship to prior documents

This analysis agrees with, and does not re-derive, the measurements in
[story-diversity-analysis.md](story-diversity-analysis.md) (as corrected by
[story-diversity-review-errata.md](story-diversity-review-errata.md)) and the fact base in
[story-diversity-plan-v2.md](story-diversity-plan-v2.md). What it adds: the research-translation and
provenance root causes (2.1, 2.4), the reachability and authoring-path causes (2.6, 2.7, found by the
completeness review), the three-way split of graph vs experience vs scene structure with all shipped
metrics at the graph layer (1, 4, 6.3), the floors-as-targets reading (2.2, 3), the compounding-loop
model (5), and the re-sequenced program (6). Open items already registered are cited by their UW rows
rather than duplicated. The first version of this document predates none of its sources but was
corrected same-day by a three-team adversarial and completeness review; the banner records the
material corrections, in keeping with this repo's errata practice.
