---
title: "Skeleton Library Expansion Plan"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Prioritized backlog for authoring the preset story-skeleton seed set across the reading-level x topology x scale(length) matrix, with per-cell guardrails, the compact-vs-genre-faithful budget decision, and the authoring workflow, so the generators have baseline flows and the launch catalog (P9-02) has ready shells."
tags:
  - planning
  - architecture
component: Content-Pipeline
source: "docs/superpowers/specs/2026-06-23-modal-generation-tiers-design.md sections 3-5,12-13; docs/superpowers/specs/2026-06-30-skeleton-structure-diagrams-design.md section 4; src/cyo_adventure/validator/band_profile.py; src/cyo_adventure/storybook/models.py; docs/planning/PROJECT-PLAN.md (P9-02); docs/planning/drafting-guide.md"
---

## Context

A **preset skeleton** is a Storybook instance with structural content authored and
prose slots empty (`<<FILL role=... words=... beats='...'>>` on non-ending nodes).
`generation.skeleton.load_skeleton()` runs the whole file through the blocking gate
(`run_gate`, Layer 1 + Layer 2 including the band profile) at load time, so a
committed preset is guaranteed structurally sound. A later prose-fill pass (Stage B)
turns the shell into a shippable story: shell + prose = story.

Per the modal-generation-tiers design (section 4), the skeleton is a **data artifact**
whose classification `{topology_class, node_count, reading_band, ending_count,
decision_count, state_depth, ...}` "drives library selection and model routing," and
the intended creation path is "a small **hand-authored seed set per cell** first
(proves the pipeline against the real validator), then a procedural skeleton
generator ... as the scaling step." **This plan is that hand-authored seed set.**

## Target model: Reading level x Topology x Scale (length)

The organizing matrix (modal-gen-tiers section 3) has three axes; the generation
flow selects a skeleton by `(theme, reading_band, length; coverage-aware)`
(section 5). So **length/scale is a first-class selection axis, not a side effect**:

1. **Reading level (age band)** - 6 bands: `3-5`, `5-8`, `8-11`, `10-13`, `13-16`, `16+`.
   Selects topology family, scale, fail-state policy, words-per-node, and model tier.
2. **Topology** - 4 shapes (Ashwell): `time_cave`, `gauntlet`, `branch_and_bottleneck`,
   `loop_and_grow`.
3. **Scale (length)** - the node-count/word-count target. Length defines the expected
   node count; **for a given length, older bands get more nodes and more words per
   node.** Named tiers (proposed): **Short / Medium / Long / Very Long**.

Each `(band x length)` pair is a **cell**. The seed-set goal is >=1 authored skeleton
per populated cell (design decision: "all six bands ship in v1 with at least one
authored sample each," section 13), broadening to multiple flows/topologies per cell
as the library matures.

### Genre-faithful per-band anchors (design target, section 3)

| Band | Characteristic scale | Nodes (genre-faithful) | Endings | Decisions/path | Tier | Words/node | Fail-state policy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3-5 | very short | ~10-20 | 3-6 | ~2-4 | 1 | ~75-100 | no death/capture; comic, always-recover |
| 5-8 | short | ~42-46 | 9-12 | ~3-6 | 1 | ~100 | no death/capture; try-again, comic |
| 8-11 | short (or ~45 at 250w) | ~90-120 | ~20 | ~4-5 (max 7) | 1 | ~125-150 | failure/entrapment, adventure-forward (no death) |
| 10-13 | medium | ~110-180 | ~19-28 | ~5-10 | 2 (light) | ~175 | horror variety, logical |
| 13-16 | long | ~350-456 | 1 win + many fails | ~12-25 | 2 (full) | ~225 | resource-based, lethal |
| 16+ | very long | ~400+ | many fails + few wins | ~20-30+ | 2 (full) | ~250 | lethal, resource-based, mature |

## Implementation reality: only the "compact slice" landed

The full matrix above is **specified but only partially implemented**; the compact
MVP slice shipped via PR #14 (the compact-scale generation slice). Concretely:

| Architectural element | Specified | In code today |
| --- | --- | --- |
| Age band as policy profile | yes (section 3) | partial: `band_profile.py`, 6 bands, but **compact node budgets** |
| Per-band genre-faithful node budgets | yes (~90-456 nodes) | **no** - compact caps only (see below) |
| Length/scale as a first-class axis | yes (sections 3, 5) | **no** - only `estimated_minutes: int`, no `Length` enum |
| Per-length node budgets (scale x band) | yes | **no** - one `min/max` per band |
| `words_per_node` target enforced | yes (section 3) | **no** - advisory prose text only, no gate |
| Band x length coverage matrix / cells | yes (diagrams spec s4) | **no** - catalog shows band-only coverage |
| `select_skeleton(band, length, theme)` | yes (section 5) | **no** - not implemented |
| Procedural skeleton generator | yes (phase 6) | **no** |

**The gating conflict.** `load_skeleton` enforces `band_profile` node caps, which are
the *compact* values, far below genre-faithful scale:

| Band | Compact `band_profile` nodes (enforced today) | Genre-faithful target |
| --- | --- | --- |
| 3-5 | 8-20 | ~10-20 (matches) |
| 5-8 | 12-30 | ~42-46 (**exceeds cap**) |
| 8-11 | 15-30 | ~90-120 (**3-4x over cap**) |
| 10-13 | 25-50 | ~110-180 (**over cap**) |
| 13-16 | 30-60 | ~350-456 (**6-8x over cap**) |
| 16+ | 30-60 | ~400+ (**7x+ over cap**) |

A genre-faithful `8-11` or `16+` skeleton **cannot be committed today** - the gate
rejects it. The existing shells confirm the compact reality: Sunken Signal (16+) is
32 nodes, not 400+.

## Current coverage on the matrix (3 of 6 bands, compact scale)

| Skeleton | Band | Length (compact) | Topology | Tier | Nodes | Endings (+/n/-) |
| --- | --- | --- | --- | --- | --- | --- |
| The Lost Mitten | 3-5 | very short | loop_and_grow | 1 | 11 | 3/0/0 |
| The Clocktower Cipher | 10-13 | (compact medium) | branch_and_bottleneck | 1 | 25 | 3/1/4 |
| The Sunken Signal | 16+ | (compact) | branch_and_bottleneck | 2 | 32 | 1/1/12 |

- **Bands (3/6):** missing `5-8`, `8-11`, `13-16`.
- **Topologies (2/4):** missing `time_cave`, `gauntlet`.
- **Tiers:** tier 2 only at `16+`; `10-13` (a tier-2 band by design) is authored tier-1.
- **Lengths:** every cell is a single compact point; no length axis is exercised.

## Decided approach (2026-07-02): restore full scale first, on a separate branch

Two decisions set the sequencing for all work below:

1. **Restore the full scale model before authoring any new skeleton.** Land
   genre-faithful per-`(band,length)` node budgets, a `Length` tier axis, and
   `words_per_node` targets across **all six bands** (modal-gen-tiers phases 3 & 7),
   then author skeletons at real scale into `(band x length)` cells. No new compact
   skeletons are authored as an interim.
2. **The enabler lives on its own branch, landed first.** The `band_profile.py` +
   `models.py` scale changes ship as their own reviewable PR; this authoring branch
   (`feat/skeleton-library-expansion`) then **rebases onto it** and stays
   content-only. This keeps a schema/validator change from being reviewed tangled
   with story content.

**Consequence - existing compact skeletons must be reconciled.** Raising per-band
node floors to genre-faithful scale would make the two larger existing shells fail
the new floor: Clocktower Cipher (`10-13`, 25 nodes vs genre ~110-180) and Sunken
Signal (`16+`, 32 nodes vs ~400+). The enabler branch must therefore decide, as part
of its design, one of:

- **Grandfather via a below-Short tier** - the existing shells occupy a small,
  legitimate cell of their band; or
- **Schedule a re-scale** - treat Clocktower and Sunken Signal as re-author targets
  to genre scale (Lost Mitten at `3-5`/11 nodes already fits genre ~10-20 and needs
  no change).

**Resolved (see the MVP/Test tier below):** grandfather via a below-Short,
non-production **MVP/Test tier**. All three current skeletons are classified as MVP
dev seeds, so the catalog + drift-guard tests stay green without rescaling.

## Story-scale framework (band x length x style) - FINAL

The finalized scale model the P0 enabler will encode. It supersedes the raw
research anchors above (which remain the measured baseline it derives from). Three
axes, three "clocks", and a flow vocabulary.

### Axes

1. **Band** (reading level) - 6, given.
2. **Length** - 3 tiers **Short / Medium / Long**, defined by a **total-word budget**
   (world size), not single-read time. Young bands (3-5, 5-8) cap at Medium. Epic
   scale is a **series** of Long stories, not a 4th tier.
3. **Style** (`narrative_style`) - **Prose** vs **Gamebook**, an explicit field
   meaningful only for `13-16`/`16+`; all lower bands are implicitly Prose. Style sets
   words/node, so the same length is more, shorter nodes (gamebook) or fewer, denser
   nodes (prose).

Plus a non-production **MVP/Test tier** below Short (see below).

### MVP/Test tier (below Short, non-production)

A single band-independent tier below Short, for **prototyping, pipeline/integration
testing, and generator development only**. Marked `production_eligible = false`
(`tier = "mvp"`): `load_skeleton` accepts it, but production story selection excludes
it, so no MVP-scale story reaches a child-facing catalog.

- **Node envelope**: ~8-45 nodes, band-independent. Words/node still inherits the band
  mean (an `16+` MVP node is denser than a `3-5` one).
- **`min-to-complete`**: relaxed to ~4; the arc-floor substance requirement is **waived**
  (MVP shells exist to be short).
- **Endings**: ~2-6. **Style**: prose only.
- The three current hand-authored skeletons live here as development seeds (Lost Mitten
  11, Clocktower 25, Sunken Signal 32). This resolves the Pilot-vs-rescale question:
  **classify the current skeletons as MVP seeds**, do not rescale them.

### The three clocks

- **Fastest finish** = shortest path to a *satisfying* completion (success/completion
  valence). A per-cell **floor** (`min-to-complete` nodes) enforcing a full arc
  (setup -> rising -> climax -> resolution). Fail-*fast* is allowed; a quick, hollow
  *win* is not. Substance is added with mandatory **linear passages**, not more
  decisions.
- **Total-node envelope** = world size, `total_words / words_per_node`. A *derived*
  range; skeletons vary within it by topology.
- **Whole-world** = replay-to-exhaustion, `total_words / reading_pace`. Identical for
  prose and gamebook (same total words). Tracks ending count (~replays to exhaust).

### Words per node (advisory story-mean; anchor 100 at core)

Enforced as a story-level **mean** within the advisory band, plus a per-node hard
**max** (wall guard); no hard per-node min (a one-line beat is legitimate).

| Band | Style | Mean | Advisory band | Per-node max |
| --- | --- | ---: | --- | ---: |
| 3-5 | prose | 40 | 28-55 | 90 |
| 5-8 | prose | 70 | 50-95 | 155 |
| 8-11 | prose | 100 | 70-135 | 220 |
| 10-13 | prose | 100 | 70-135 | 220 |
| 13-16 | prose | 140 | 100-185 | 310 |
| 13-16 | gamebook | 65 | 45-90 | 145 |
| 16+ | prose | 175 | 125-230 | 385 |
| 16+ | gamebook | 80 | 55-110 | 175 |

### Reading pace (approx; standard fluency norms, not project-measured)

| Band | 3-5 | 5-8 | 8-11 | 10-13 | 13-16 | 16+ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| words/min | ~100 (aloud) | ~90 | ~120 | ~150 | ~190 | ~220 |

### Master cell table

`min->complete` = arc-floor shortest success path (nodes). `total nodes` = derived
world-size envelope. Endings for prose are counts; gamebooks are "few wins + many
fails" (~25-35% of nodes are terminals). `dagger` cells exceed the ~460-node
hand-authoring ceiling -> procedural-generator / series scale, out of scope for
hand-authored seeds.

| Band | Length | Style | min->complete | fastest finish | total nodes | endings | whole-world |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| 3-5 | Short | prose | 6 | ~2-3 min | 10-23 | 2-4 | ~5-9 min |
| 3-5 | Medium | prose | 7 | ~3 min | 23-45 | 4-6 | ~9-18 min |
| 5-8 | Short | prose | 7 | ~5 min | 29-50 | 6-10 | ~20-40 min |
| 5-8 | Medium | prose | 9 | ~7 min | 50-86 | 10-16 | ~40-65 min |
| 8-11 | Short | prose | 9 | ~8 min | 60-100 | 12-18 | ~50-85 min |
| 8-11 | Medium | prose | 12 | ~10 min | 100-160 | 18-28 | ~85-135 min |
| 8-11 | Long | prose | 14 | ~12 min | 160-240 | 28-40 | ~2.2-3.3 hr |
| 10-13 | Short | prose | 11 | ~7 min | 90-140 | 14-22 | ~60-95 min |
| 10-13 | Medium | prose | 14 | ~9 min | 140-220 | 22-32 | ~95-145 min |
| 10-13 | Long | prose | 17 | ~11 min | 220-340 | 32-48 | ~2.5-3.8 hr |
| 13-16 | Medium | prose | 15 | ~11 min | 115-170 | 20-32 | ~85-125 min |
| 13-16 | Medium | gamebook | 24 | ~8 min | 245-370 | many fails | ~85-125 min |
| 13-16 | Long | prose | 20 | ~15 min | 170-270 | 30-48 | ~2.1-3.3 hr |
| 13-16 | Long | gamebook | 32 | ~11 min | 370-585 dagger | many fails | ~2.1-3.3 hr |
| 16+ | Medium | prose | 18 | ~14 min | 135-215 | 24-40 | ~110-175 min |
| 16+ | Medium | gamebook | 29 | ~11 min | 300-475 dagger | many fails | ~110-175 min |
| 16+ | Long | prose | 23 | ~18 min | 215-345 | 36-60 | ~2.9-4.6 hr |
| 16+ | Long | gamebook | 37 | ~14 min | 475-750 dagger | many fails | ~2.9-4.6 hr |

### Constants (research-locked, all cells)

- **Decisions per path: ~4-8** (length adds breadth, not depth; do not inflate).
- **Choices per decision: 2-3** (rare 5-12 mystery hubs are premise-specific).
- **Setup before first choice: ~2-3 nodes.**
- **Endings via reconvergent leaves, not depth.**

### Topologies (6 in the enum) + flow primitives

Node-connection primitives: **linear passage** (1->1), **branch** (1->N), **bottleneck**
(M->1 reconvergence), **loop** (back-edge; needs state), **terminal** (1->0 ending),
**restart-on-fail** (negative ending -> start/checkpoint). Topologies compose them:

| Topology | Built from | Fastest-finish | Reread driver |
| --- | --- | --- | --- |
| time_cave | branch, terminal | low | many divergent endings |
| loop_and_grow | branch, loop, bottleneck, terminal | low-med | state growth per loop |
| branch_and_bottleneck (incl. **quest** variant) | branch, bottleneck, terminal | med | different routes, same beats |
| open_map | hub, branch, loop/return, bottleneck, terminal | med | explore in any order |
| sorting_hat | branch (sort), parallel subtrees, terminal; **no cross-track bottleneck** | med | play each track |
| gauntlet | linear spine, branch-to-fail, terminal (many), restart-on-fail | high | master the one path |

`sorting_hat` costs `sort + N x (track arc)` nodes, so it buys **replay diversity**
(a different story per track, strongest for older readers) at a node premium; it lives
in Medium/Long cells, not Short. `floating_modules` is documented-but-deferred
(advanced, stateful, procedural-generator scope).

### Per-band topology + flow allowances

| Band | Topologies | Loops | Restart-on-fail | Reconvergence |
| --- | --- | --- | --- | --- |
| 3-5 | loop_and_grow, time_cave | gentle try-again | none (no death/capture) | minimal |
| 5-8 | time_cave, loop_and_grow, open_map | comic | soft try-again only | light |
| 8-11 | branch_and_bottleneck, time_cave, open_map, sorting_hat | optional (T2) | failure/entrapment, no death | light-rising |
| 10-13 | branch_and_bottleneck, open_map, sorting_hat | yes (state) | yes, logical | moderate |
| 13-16 | branch_and_bottleneck (prose), gauntlet (gamebook), sorting_hat, open_map | yes | yes, lethal (gamebook) | prose moderate / gamebook low |
| 16+ | branch_and_bottleneck / gauntlet, sorting_hat | yes | yes, lethal | prose moderate / gamebook low |

### Provenance (measured vs product-defined)

| Band | Evidence |
| --- | --- |
| 8-11 | **measured, high** (JHM + UCSB agree on nodes; words/node anchor 100 research-backed) |
| 5-8 | node counts UCSB-measured; words/endings estimated |
| 10-13 | medium (mix of measured and page-turn metadata) |
| 13-16 | gamebook metadata, medium; no graph-theory anchor |
| 3-5, 16+ | **product-defined**, no research anchor |

Reading pace and the intermediate length grid are extrapolations from these anchors.

### Existing-skeleton reconciliation

| Skeleton | Band | Nodes | Production floor | Outcome |
| --- | --- | --- | --- | --- |
| The Lost Mitten | 3-5 | 11 | Short (10) | conforms to `3-5` Short, but classified **MVP** as a dev seed |
| The Clocktower Cipher | 10-13 | 25 | Short (90) | below floor -> **MVP** seed (non-production) |
| The Sunken Signal | 16+ | 32 | Medium prose (135) | far below -> **MVP** seed (non-production) |

**Resolved:** all three current skeletons are classified into the non-production
**MVP/Test tier** (`tier = "mvp"`, `production_eligible = false`), not rescaled. They
stay as cheap prototyping/dev seeds; the production floors above are unaffected.

### Series (campaign continuity)

A story may carry a **series tag**; a series spans multiple books that share
characters/world and continue one storyline. Series is *how* epic scale is built (a
chain of Medium/Long books), not a length tier.

**The single-entry invariant.** In a non-final series book, **every
successful-completion ending converges to the next book's single `series_entry_node`**
(many endings -> one entry). However the reader finished book N, book N+1 picks up from
one place; **carried state** captures the differences, not the narrative entry. This
keeps book N+1 authored once instead of once per predecessor ending. Non-success
endings (setback / death / local fail) do not continue.

**Series metadata** (data model now; full series generation is a later phase):

- `series_id` + `book_index` (1..N).
- `series_entry_node`: the single continuation entry (book 1 uses its normal
  `start_node`; later books declare this node).
- successful-completion endings flagged as series-continuing.
- **state-export contract**: which variables persist book N -> book N+1.

**Series-level (meta-skeleton) validation.** Books are nodes, completion->entry links
are edges; v1 is a **linear chain** (single entry per book). Rules: each non-final book
has >=1 continuing success ending; all continuing endings target the next book's single
`series_entry_node`; the exported state the next book reads is declared and
type-compatible; each book independently passes its own band/length/style/topology gate.

**Per-band applicability:**

- 3-5 / 5-8 (tier 1, no state): **episodic** series only (same characters, next
  adventure); the single-entry rule holds, but nothing carries.
- 8-11+: full series with state carry.
- 13-16 / 16+ gamebook: the canonical campaign case (stats / inventory / flags carry,
  the Fighting Fantasy / Lone Wolf model).

**Enabler-branch sub-decisions:** dual standalone+continuation entry vs
continuation-only for later books; default/missing-state handling if a later book is
played standalone; max books per series; whether the band may rise across a series.

## Prioritization

Ordering principle: **land the scale enabler first (separate branch), then finish
the seed-set floor (one per band) before depth**, making each early build cover a
missing topology. All authoring targets genre-faithful scale.

### P0 - Scale enabler (separate branch, lands first; code, not authoring)

Its own PR; this authoring branch rebases onto it. Encodes the **Story-scale
framework** above into `band_profile.py` + `storybook/models.py` (+
`skeleton_catalog.py`):

- **Length axis** (`short`/`medium`/`long`) as story metadata and a `select`-time
  parameter; young bands cap at Medium.
- **`narrative_style`** enum (`prose`/`gamebook`) meaningful for `13-16`/`16+`;
  budgets key on `(band, length, style)` for those bands.
- **`Topology` enum add** `open_map` + `sorting_hat` (quest folds into
  `branch_and_bottleneck`; `floating_modules` documented-deferred), plus the
  deterministic classifier + per-band allowance checks.
- **Derived total-node budgets** per `(band, length, style)` from the master cell
  table, replacing the single compact `min_nodes`/`max_nodes` per band.
- **`words_per_node`** as an advisory story-**mean** within the per-`(band,style)`
  band, plus a per-node hard **max** (wall guard); no hard per-node min.
- **`min-to-complete` floor**: shortest path to a satisfying (success/completion)
  ending must meet the per-cell arc floor, added via mandatory linear passages.
- **Breadth-scaled `min_endings`/`min_decisions`** per cell (replacing the flat 1-4);
  decisions/path held at ~4-8 across all cells.
- Coverage tracking: extend `skeleton_catalog.py` to render the `band x length x style`
  grid, not the 1D band list.
- **Series metadata + meta-skeleton validator** (data model now, generation deferred):
  `series_id`/`book_index`/`series_entry_node`, the success-ending continuation flag,
  the state-export contract, and the single-entry convergence rule.
- **MVP/Test tier** (below Short, non-production): a `tier = "mvp"` /
  `production_eligible = false` marker with a band-independent ~8-45 node envelope,
  relaxed `min-to-complete` (~4, arc floor waived), accepted by `load_skeleton` but
  excluded by production selection. The 3 existing compact skeletons are classified
  here, so the catalog + drift-guard tests stay green without rescaling them.

Authoring (P1-P3) does not begin until P0 has landed and this branch is rebased.

### P1 - Seed-set floor: the 3 missing bands (authoring, genre-faithful scale)

Close band coverage; each build also closes a missing topology. Scale per the
chosen path.

| # | Band | Tier | Topology (new) | Length | Theme direction | Rationale |
| --- | --- | --- | --- | --- | --- | --- |
| P1-1 | 8-11 | 1 | **time_cave** | short (genre ~90-120 if Path B) | exploration / discovery | Core research-measured band, zero coverage, adds time_cave. Highest launch value. |
| P1-2 | 5-8 | 1 | loop_and_grow | short (~42-46) | gentle repeat-quest (gather/help/return) | Early-reader floor; proven kid-friendly shape scaled up from Lost Mitten. |
| P1-3 | 13-16 | 2 | **gauntlet** | long | stakes/adventure with resource+inventory state | Adds the 4th topology + upper-band floor + a second tier-2 band. Heaviest lift; schedule last in P1. |

After P1: all 6 bands seeded, all 4 topologies present, tier-2 in two bands.

### P2 - Cell depth for core launch bands (authoring)

Second flow for the bands central to a kids' reading app, varying length and
topology within the cell so the catalog has intra-band variety.

| # | Band | Tier | Topology | Length | Notes |
| --- | --- | --- | --- | --- | --- |
| P2-1 | 8-11 | 2 | branch_and_bottleneck | medium | Introduces tier-2 state to the core band; a longer cell than P1-1. |
| P2-2 | 10-13 | 2 | gauntlet or time_cave | medium/long | Today's only 10-13 shell is tier-1 B&B; vary tier, topology, and length. |
| P2-3 | 5-8 | 1 | time_cave | short | Second early-reader shell, different shape than P1-2. |

### P3 - Breadth across remaining cells (authoring)

Second flow for `3-5` (a `time_cave`), `13-16` (`branch_and_bottleneck`), and `16+`
(`gauntlet` or `loop_and_grow`), plus additional length points, as catalog breadth
and the procedural generator warrant.

## Per-band authoring guardrails (compact `band_profile`, enforced today)

These are the **current, pre-enabler** caps that `load_skeleton` enforces; the P0
enabler branch raises the node budgets to genre-faithful per-`(band,length)` values
(section 3 anchors) and adds the `words_per_node` target. The content-ceiling,
depth, ending, and decision floors below are policy and carry forward unchanged; only
the node budgets change. A skeleton that violates its band profile is blocked by
`load_skeleton`.

| Band | Nodes (min-max) | Max depth | Ceiling (violence / scary / peril) | Forbidden endings | Min endings | Min decisions |
| --- | --- | --- | --- | --- | --- | --- |
| 3-5 | 8-20 | 4 | none / mild / mild | death, capture | 2 | 1 |
| 5-8 | 12-30 | 6 | mild / mild / mild | death, capture | 2 | 2 |
| 8-11 | 15-30 | 6 | mild / moderate / moderate | death | 3 | 3 |
| 10-13 | 25-50 | 8 | moderate / moderate / moderate | (none) | 3 | 3 |
| 13-16 | 30-60 | 10 | moderate / intense / intense | (none) | 4 | 4 |
| 16+ | 30-60 | 12 | moderate / intense / intense | (none) | 4 | 4 |

Fail-state note: the two youngest bands forbid `death` **and** `capture`, and `8-11`
forbids `death`. A `gauntlet` in those bands must express fail branches as `setback`
endings (negative valence, gentle "try again"), never death/capture - which is why
the gauntlet build is slotted at `13-16` (P1-3), where lethal/intense is permitted.

## Authoring workflow (per skeleton)

Each skeleton is a self-contained, independently-shippable unit:

1. **Draft** `skeletons/<band>/<slug>.json` to schema v2.0: `metadata` (band, tier,
   topology, `estimated_minutes`, `content_flags`, `ending_count`), `variables`
   (tier 2 only; tier 1 must declare none), `start_node`, and `nodes` with
   `<<FILL role=... words=... beats='...'>>` bodies on non-ending nodes.
2. **Validate structurally** by loading through the gate. A passing `load_skeleton`
   means budget, reachability, termination, content ceiling, ending/decision floors,
   and forbidden-ending policy are all satisfied - the validator is the spec.
3. **Regenerate diagrams + catalog** (drift-guarded in CI):

   ```bash
   PYTHONPATH=. uv run python scripts/render_skeleton_diagrams.py
   ```

4. **Test**: add a fixture reference if the skeleton exercises a specific structural
   branch; run the suite.
5. **Commit** one skeleton per signed commit (`feat(skeletons): ...`).

## Resolved decisions (2026-07-02)

- **Scale approach: restore full scale first**, across all six bands, before authoring
  any new skeleton. No interim compact authoring.
- **Enabler scope: separate branch, landed first;** this authoring branch rebases onto
  it and stays content-only.
- **Length: 3 tiers** (Short/Medium/Long); young bands cap at Medium; epic = a series,
  not a 4th tier. Defined by total-word budget; node count derived.
- **Style: explicit `narrative_style`** (prose/gamebook) for `13-16`/`16+` only.
- **Topologies: 6** (time_cave, gauntlet, branch_and_bottleneck, loop_and_grow,
  open_map, sorting_hat); quest folds into branch_and_bottleneck; floating_modules
  deferred.
- **Fastest-finish floor**: shortest satisfying-completion path meets a per-cell arc
  floor (full setup->rising->climax->resolution), via mandatory linear passages;
  decisions/path stays ~4-8.
- **Words/node: advisory mean** (anchor 100 at 8-11/10-13), per-node max wall-guard,
  no hard per-node min. See the framework's master cell table for all values.
- **Series (campaign continuity):** a series tag chains multiple books; every
  successful-completion ending of a non-final book converges to the next book's single
  `series_entry_node`, with state carried across. Series is epic scale (a linear chain),
  not a length tier; schema now, generation later.
- **MVP/Test tier (below Short, non-production):** a band-independent ~8-45 node tier
  (`tier = "mvp"`, `production_eligible = false`) for prototyping/dev/testing; relaxed
  `min-to-complete` and waived arc floor; excluded from production selection. The 3
  existing compact skeletons are classified here instead of being rescaled. This closes
  the former Pilot-vs-rescale open decision.

## Open decisions

1. **Launch band concentration.** P9-02's "12 stories, 4 per band" was the initial
   3-band launch (3 x 4). Confirm which 3 bands lead launch (core reading bands
   `5-8`/`8-11`/`10-13` are the natural set) so P2/P3 depth targets them first.
