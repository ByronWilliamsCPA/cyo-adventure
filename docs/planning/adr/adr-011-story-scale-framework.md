---
title: "ADR-011: Story-scale framework (reading band x length x style)"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the story-scale framework that governs skeleton and story size: the
  reading-band x length x narrative-style matrix, total-words-primary with derived node
  counts, the three completion clocks, the topology set and flow-primitive vocabulary,
  and the series single-entry invariant. Formalizes and supersedes the compact per-band
  budget slice currently in band_profile.py."
tags:
  - planning
  - architecture
  - decisions
  - generation
  - validation
---

# ADR-011: Story-scale framework (reading band x length x style)

> **Status**: Accepted (2026-07-03)
> **Date**: 2026-07-02
> **Relates to**: [ADR-001](./adr-001-story-format-json-storybook.md) (adds `length`,
> `narrative_style`, and `series` metadata plus two `Topology` enum values),
> [ADR-006](./adr-006-conditions-inhouse-evaluator.md) (series state-carry uses declared
> variables/conditions). **Supersedes** the compact per-band budgets in
> `validator/band_profile.py` (the "compact slice", the only part of an earlier
> internal reading-level x topology x scale design memo that landed).

## TL;DR

Story size is a deliberate product axis, not a side effect of generator behaviour. A
story is placed on a **reading-band x length x narrative-style** matrix. **Length is
defined by a total-word budget; node count is derived** (`nodes = total_words /
words_per_node`). Three "clocks" govern the experience: a **fastest-finish arc floor**
(shortest path to a satisfying completion must tell a full story), a **total-node
envelope** (world size, with per-cell variance across skeletons), and a **whole-world
replay** measure. Decisions-per-path is held constant (~4-8); length adds breadth, not
depth. Six topologies compose from six flow primitives, gated by per-band safety
allowances. A **series** chains books, with every successful-completion ending of a
non-final book converging on the next book's single entry node.

## Context

The full model was specified in an earlier internal design memo but only a **compact
slice** shipped: `band_profile.py` holds one small node range per band (8-11 <= 30, 16+
<= 60), with no length or style axis, no words-per-node enforcement, and a band-only
coverage view. Genre-faithful scale is far larger (8-11 ~90-120 nodes, 13-16 ~350-456,
16+ ~400+), so genre-scale skeletons are rejected by `load_skeleton` today.

The empirical basis (recorded in `docs/planning/research/`):

- **JHM 2019** measured 40 classic CYOA books (ages 9-12): ~90-120 page-nodes, median
  ~20 endings (11-42), ~5 decisions/playthrough (7-8 longest), essentially a tree (max
  indegree 1.5). This anchors the 8-11 and 10-13 bands with high confidence.
- The four-source reconciliation adds words/node (~100-150), total words (~8-15k at
  8-11), the age-gated fail-state policy, and the finding that many endings come from
  **reconvergent leaves, not depth**.
- **5-8** node counts are measured (medium confidence); **13-16** rests on gamebook
  metadata; **3-5 and 16+ have no research** and are product-defined.

The framework must be durable because size decisions drive reading fit, safety policy,
generation cost, and catalog shape, and because the compact slice already demonstrated
that an unrecorded model silently collapses (the length axis was lost).

## Decision

### 1. Three axes

- **Reading band** (6): `3-5`, `5-8`, `8-11`, `10-13`, `13-16`, `16+`.
- **Length** (3 production tiers): `short`, `medium`, `long`, defined by a **total-word
  budget**. Young bands (`3-5`, `5-8`) cap at Medium. Epic scale is a **series**, not a
  4th tier. A non-production **MVP/Test tier** sits below Short (section 1a).
- **`narrative_style`** (explicit field): `prose` vs `gamebook`, meaningful only for
  `13-16`/`16+`; all lower bands are implicitly prose. Style sets words/node, so one
  length is either fewer/denser nodes (prose) or more/shorter nodes (gamebook).

### 1a. MVP/Test tier (below Short, non-production)

A single band-independent tier below Short, for prototyping, pipeline/integration
testing, and generator development. It is **not production-eligible**: skeletons and
stories in this tier are marked `production_eligible = false` (a `tier = "mvp"` marker),
`load_skeleton` accepts them, but production story selection excludes them so no
MVP-scale story ever reaches a child-facing catalog.

- **Node envelope**: ~8-45 nodes, band-independent (the point is exercising the plumbing,
  not reading fit). Words/node still **inherits the band mean** from section 3, so an
  `16+` MVP node is denser than a `3-5` one.
- **`min-to-complete`**: relaxed to ~4 nodes; the arc-floor substance requirement of the
  three clocks (section 4) is **waived** here, because MVP shells exist to be short.
- **Endings**: ~2-6. **Style**: prose only (gamebook needs scale to be meaningful).
- The three current hand-authored skeletons live here as development seeds: Lost Mitten
  (`3-5`, 11 nodes), Clocktower (`10-13`, 25), Sunken Signal (`16+`, 32). This is the
  decision that closes the earlier Pilot-vs-rescale question: **adopt an MVP tier and
  classify the current skeletons into it**, rather than rescaling them to production floors.

### 2. Total words primary, node count derived

`nodes = total_words / words_per_node`. The gate enforces the derived node envelope, but
the design anchor is words. This binds nodes, words, and words/node by one equation so
the axes cannot silently disagree (the failure mode that lost the length axis before).

### 3. Words per node (advisory story-mean; anchor 100 at the research core)

Enforced as a story-level **mean** within the advisory band, plus a per-node hard
**max** (wall guard); **no** hard per-node min (a one-line beat is legitimate).

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

### 4. The three clocks

- **Fastest finish** = shortest path to a *satisfying* completion (success/completion
  valence), a per-cell floor (`min-to-complete` nodes) that must contain a full arc
  (setup -> rising -> climax -> resolution). Substance is added with mandatory **linear
  passages**, not extra decisions. Fail-*fast* is allowed; a quick, hollow *win* is not.
- **Total-node envelope** = world size, derived; skeletons vary within it by topology.
- **Whole-world** = replay to exhaustion (`total_words / reading_pace`), identical for
  prose and gamebook; tracks ending count.

### 5. Master cell table

These are the **production** cells; the below-Short MVP/Test tier (section 1a) is
deliberately smaller than every row here and is excluded from this table.
`min->complete` = arc-floor shortest success path (nodes). `total nodes` = derived
envelope. Gamebook endings are "few wins + many fails" (~25-35% of nodes are terminals).
`dagger` = exceeds the ~460-node hand-authoring ceiling; procedural-generator / series
scale, not a hand-authored seed.

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

Reading-pace anchors (approx, standard fluency norms, not project-measured): 3-5 ~100
wpm (read aloud), 5-8 ~90, 8-11 ~120, 10-13 ~150, 13-16 ~190, 16+ ~220.

### 6. Constants (research-locked, all cells)

Decisions per path **~4-8** (length adds breadth, not depth; do not inflate); choices
per decision **2-3**; setup before first choice **~2-3 nodes**; endings via reconvergent
leaves, scaling with node count (prose ~15-22%).

### 7. Topologies (6) and flow primitives

Flow primitives: **linear passage** (1->1), **branch** (1->N), **bottleneck** (M->1),
**loop** (back-edge; needs state), **terminal** (1->0), **restart-on-fail** (negative
ending -> start/checkpoint).

| Topology | Built from | Fastest-finish | Reread driver |
| --- | --- | --- | --- |
| time_cave | branch, terminal | low | many divergent endings |
| loop_and_grow | branch, loop, bottleneck, terminal | low-med | state growth per loop |
| branch_and_bottleneck (incl. **quest** variant) | branch, bottleneck, terminal | med | different routes, same beats |
| open_map | hub, branch, loop/return, bottleneck, terminal | med | explore in any order |
| sorting_hat | branch (sort), parallel subtrees, terminal; no cross-track bottleneck | med | play each track |
| gauntlet | linear spine, branch-to-fail, terminal (many), restart-on-fail | high | master the one path |

`open_map` and `sorting_hat` are **added** to the enum; `quest` folds into
`branch_and_bottleneck`; `floating_modules` is documented-but-deferred. Per-band
allowances gate the dangerous primitives: no `death`/`capture` endings for `3-5`/`5-8`,
no `death` for `8-11`; loops require state (tier 2); restart-on-fail is lethal only from
`13-16` up.

Per-band topology and flow allowances (which shapes an authored skeleton may use):

| Band | Topologies | Loops | Restart-on-fail | Reconvergence |
| --- | --- | --- | --- | --- |
| 3-5 | loop_and_grow, time_cave | gentle try-again | none (no death/capture) | minimal |
| 5-8 | time_cave, loop_and_grow, open_map | comic | soft try-again only | light |
| 8-11 | branch_and_bottleneck, time_cave, open_map, sorting_hat (Medium/Long only) | optional (T2) | failure/entrapment, no death | light-rising |
| 10-13 | branch_and_bottleneck, open_map, sorting_hat (Medium/Long only) | yes (state) | yes, logical | moderate |
| 13-16 | branch_and_bottleneck (prose), gauntlet (gamebook), sorting_hat (Medium/Long only), open_map | yes | yes, lethal (gamebook) | prose moderate / gamebook low |
| 16+ | branch_and_bottleneck / gauntlet, sorting_hat (Medium/Long only) | yes | yes, lethal | prose moderate / gamebook low |

The `3-5` and `5-8` Loops entries ("gentle try-again", "comic") are the non-stateful
try-again kind, legal at Tier 1; they are distinct from the stateful progress loops
referenced by "loops require state (tier 2)" above, which first apply at `8-11`
("optional (T2)") and are required from `10-13` up.

`sorting_hat` costs `sort + N x (track arc)` nodes, so it buys replay diversity at a node
premium and lives in Medium/Long cells, not Short; the table above annotates every band
where it appears accordingly.

### 8. Series (campaign continuity)

A `series` tag chains multiple books. **Invariant:** in any non-final book, every
successful-completion ending converges on the next book's single `series_entry_node`
(many endings -> one entry), with declared state carried across. Series metadata:
`series_id`, `book_index`, `series_entry_node`, the continuation flag, and the
state-export contract. The series is a **meta-skeleton** (books are nodes,
completion->entry links are edges); v1 is a linear chain. Each book independently passes
its own band/length/style/topology gate. Young/tier-1 bands get **episodic** series (no
state carry). Schema/validator now; series generation is a later phase.

### 9. Provenance

Cells are tagged by evidence: `8-11` measured (high); `5-8` node counts measured, rest
estimated; `10-13` medium; `13-16` gamebook metadata; `3-5`/`16+` product-defined. This
records which numbers are empirical and which are tunable product choices.

## Consequences

- ✅ Size is a recorded, self-consistent contract (nodes derived from words and
  words/node), so the axes cannot drift apart the way the compact slice did.
- ✅ The `min-to-complete` arc floor gives the validator an anti-cheese gate: a large
  world cannot be "completed" via a 2-node shortcut to a hollow win.
- ✅ Style-as-a-field reconciles prose and gamebook as two chunkings of one word budget,
  reproducing the measured Fighting Fantasy node counts without inflating reading time.
- ✅ Series delivers epic scale as a chain of validatable books rather than an
  un-authorable mega-story.
- ✅ The below-Short **MVP/Test tier** (section 1a) resolves the Pilot-vs-rescale
  question: the three existing compact skeletons (Lost Mitten `3-5`/11, Clocktower
  `10-13`/25, Sunken Signal `16+`/32) are classified as non-production MVP seeds rather
  than rescaled, so prototyping keeps cheap shells while the production floors stay high.
- ⚠️ The MVP tier must be firewalled from production: a skeleton tagged `tier = "mvp"`
  must never be selectable for a child-facing story. The selection layer, not just the
  validator, has to enforce the exclusion.
- ⚠️ `3-5` and `16+` budgets are product-defined without research; treat as tunable and
  revisit if reader data arrives.
- ⚠️ Implementation is non-trivial: a schema change (`length`, `narrative_style`,
  `series`, two topology enum values), a rewritten `band_profile`, a topology classifier,
  and a series meta-validator. It lands on a **separate enabler branch first**; skeleton
  authoring rebases onto it and stays content-only.

## Validation

- [ ] `band_profile.py` encodes per-`(band, length, style)` budgets; `load_skeleton`
      accepts a genre-scale skeleton per the master table and rejects out-of-envelope
      node counts.
- [ ] The MVP/Test tier loads (the three current skeletons pass as `tier = "mvp"`,
      `production_eligible = false`) and production story selection excludes it; an
      MVP-scale skeleton offered for a child-facing story is refused by the selection layer.
- [ ] Words/node enforced as a story-mean with a per-node max; a one-line node passes,
      a 600-word wall fails.
- [ ] `min-to-complete` gate: a story with a hollow short win path is rejected;
      fail-fast endings are allowed.
- [ ] Topology classifier distinguishes all six patterns; per-band allowance checks
      reject a `death` ending at `3-5`/`5-8`/`8-11`.
- [ ] Series meta-validator enforces single-entry convergence and the state-export
      contract on a two-book fixture.
- [ ] Coverage view renders the `band x length x style` grid.

## Related

- [ADR-001](./adr-001-story-format-json-storybook.md): the schema this extends.
- [ADR-006](./adr-006-conditions-inhouse-evaluator.md): the evaluator series state-carry
  relies on.
- `docs/planning/research/`: the empirical anchors (JHM 2019 + four-source reconciliation).
