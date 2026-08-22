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
replay** measure. Decisions-per-path scales with the fastest-finish floor, never with
total nodes (per-cell windows derived in section 6, amended 2026-08-22); length adds
breadth, not depth. Six topologies compose from six flow primitives, gated by per-band safety
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
  **breadth, not depth** (many single-parent terminal nodes hung off a branchy spine,
  not deeper paths; see the 2026-07-27 clarification in section 7 for the corrected
  characterization of where reconvergence actually sits).
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
  three clocks (section 4) is **waived** here, because MVP shells exist to be short. The
  section 6 per-path decision windows are **waived** with it (amended 2026-08-22): a
  4-node path cannot hold a 2-3-node setup run plus multiple decisions plus a terminal,
  and the three MVP seeds never complied with the old floor.
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
envelope. Gamebook endings are "few wins + many fails"; the terminal share is governed by
the ruled **>= 12% floor** (owner ruling 2026-08-18, `UW-C291` /
`gamebook-thresholds-options.md`, encoded in `band_profile.py::_ENDINGS_FRACTION`). An
earlier draft here asserted "~25-35% of nodes are terminals"; that figure sat above the
prose fraction, had the genre relationship backwards, and now describes only the 14
pre-ruling gamebooks (measured 27.6-33.3%), while the five post-ruling gamebooks ship at
13.0-15.8% (amended 2026-08-22, section 11).
`dagger` = exceeds the ~460-node hand-authoring ceiling; procedural-generator / series
scale, not a hand-authored seed.

Two deliberate table properties, stated after the 2026-08-22 audit rather than left
silent: there are **no Short rows for `13-16`/`16+`**; at those bands' words-per-node a
Short word budget yields node counts and reading times below what the style promises its
audience (a teen wanting a shorter read is served by the `10-13` cells), and adding a teen
Short tier remains an open product choice, not an omission error. And the **`3-5`/`5-8`
endings ceilings were recalibrated upward on 2026-08-22**: the original columns implied
~17-20% ending shares while the committed strict-bar young-band shelf measures 17-41%
(`the-big-cardboard-box` alone holds 18 endings against the old cap of 6), so the
ceilings now track the measured shares; section 9 already classes these bands as
product-defined and tunable.

| Band | Length | Style | min->complete | fastest finish | total nodes | endings | whole-world |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| 3-5 | Short | prose | 6 | ~2-3 min | 10-23 | 2-8 | ~5-9 min |
| 3-5 | Medium | prose | 7 | ~3 min | 23-45 | 4-18 | ~9-18 min |
| 5-8 | Short | prose | 7 | ~5 min | 29-50 | 6-16 | ~20-40 min |
| 5-8 | Medium | prose | 9 | ~7 min | 50-86 | 10-20 | ~40-65 min |
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

### 6. Constants and per-cell decision windows

> Rewritten 2026-08-22 (see section 11). This section originally read "Constants
> (research-locked, all cells)" and pinned decisions per path at a flat "~4-8". The
> `UW-C323` audit showed that constant arithmetically unsatisfiable in 10 of 18
> production cells against this ADR's own sections 3, 5 and 10, flatly unsatisfiable
> for every gamebook cell, and unsatisfiable as a floor at `3-5`; the catalog violates
> it in both directions and the validator's PL-17 breadth floor forces gauntlets to
> break it. The window is now derived per cell, the way every other quantity in this
> ADR is derived.

**Decisions per path** is a derived per-cell window, not a universal constant. The
invariant that survives from the original wording is the real one: **decisions grow
with `min->complete`, never with total nodes** (length adds breadth, not depth; do not
inflate depth to fill a word budget).

- **Flowed prose bands (`8-11` and up)**: every stop ends in a choice (section 10), so
  the fastest finish cannot carry fewer decisions than its word budget forces. Lower
  edge = `ceil(min->complete x words-per-node mean / words-per-stop max) - 1`; upper
  edge follows the arc-ceiling multiple (`band_profile.py::ARC_CEILING_MULTIPLE`,
  ~2.5x): no root-to-ending path should carry more than ~2.5x the lower edge.

  | Cell (prose, flowed) | Fastest-finish floor | Any-path ceiling |
  | --- | ---: | ---: |
  | 8-11 Short | 6 | 15 |
  | 8-11 Medium | 8 | 20 |
  | 8-11 Long | 10 | 25 |
  | 10-13 Short | 7 | 18 |
  | 10-13 Medium | 9 | 23 |
  | 10-13 Long | 11 | 28 |
  | 13-16 Medium | 10 | 25 |
  | 13-16 Long | 13 | 33 |
  | 16+ Medium | 13 | 33 |
  | 16+ Long | 17 | 43 |

- **Page bands (`3-5`, `5-8`)**: the section 10 choice cadence governs (a choice every
  2nd-4th page at `3-5`, every 1st-2nd page at `5-8`). The floor is the band minimum
  PL-17 actually enforces (`band_profile.py` `min_decisions`: **1** at `3-5`, **2** at
  `5-8`); the cadence caps a `min->complete`-length path at roughly 2-4 choices at
  `3-5` and 4-9 at `5-8`. The original flat floor of 4 was unsatisfiable at `3-5`
  Short three independent ways (path structure, endings arithmetic, cadence).
- **Gamebook cells are exempt from any single-digit window.** Decisions per path there
  is spine-scale: catalog-measured 12-43 on the fastest satisfying path and 19-67 max.
  The operative quantity is the PL-17 breadth floor (`_DECISIONS_FRACTION` = 0.08 x
  total nodes); for `gauntlet` topology every decision lies on the one spine, so total
  decisions equals decisions-per-path by construction, and the old 4-8 window would
  have capped a gauntlet at <= 17 terminals against section 5 cells whose envelopes
  imply far more.
- The historical **"~4-8"** survives only as what it was: the JHM 2019 measurement (~5
  decisions average, 7-8 longest) of ~90-120-node middle-grade books, i.e. the
  `8-11`/`10-13` Short prose region. Under the section 10 grammar (every stop a
  choice) the same word budgets pack decisions more densely than the classic books'
  looser cadence did, which is why the derived floors above sit higher than that
  anchor's average.

**Choices per decision**: **2-4**, per the section 10 band column (2 at `3-5`, 2-3 at
`5-8`, 3 at `8-11`/`10-13`, 3-4 at `13-16`/`16+`; the pre-amendment "2-3" predated the
section 10 grammar). **Setup before first choice**: ~2-3 nodes, unchanged. **Endings**
are predominantly single-parent terminals; the **section 5 per-cell endings columns
govern counts** (encoded as `band_profile.py::_CELL_ENDING_BOUNDS`, `UW-C283`), and the
old "prose ~15-22% of nodes" is demoted to a corpus-level descriptive figure: applied
per cell it inverted against section 5 at the corners (floor above ceiling in three
cells) and the committed young-band shelf measures 17-41%. The authoring target is
single-parent, and the shipped corpus is close to it (54 of 61
skeletons hold every ending at indegree 1; see the 2026-07-27 clarification), but it is a
guideline rather than a gate. Reconvergence is an internal bottleneck/hub property
governed per topology (section 7), not an ending property; see the 2026-07-27
clarification.

Scope and enforcement: the decision windows are **authoring guidelines for new
skeletons**, scoped like the section 10 grammar they derive from (the existing catalog
is grandfathered). No validator rule gates decisions-per-path; PL-17 gates total
decision-node floors. The M4 mutation operator self-enforces a decisions-per-path
no-worsen guard and still carries the historical 4-8 constants pending per-cell
re-derivation (`UW-C326`).

### 7. Topologies (6) and flow primitives

Flow primitives: **linear passage** (1->1), **branch** (1->N), **bottleneck** (M->1),
**loop** (back-edge; needs state), **terminal** (1->0), **restart-on-fail** (negative
ending -> start/checkpoint).

| Topology | Built from | Fastest-finish | Reread driver |
| --- | --- | --- | --- |
| time_cave | branch, terminal | low | many divergent endings |
| loop_and_grow | branch, loop, bottleneck, terminal | low-med | **8-11 and up**: state growth per loop. **3-5 and 5-8**: try-again per loop, with NO growth (see the band note below) |
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

**Amendment, 2026-08-15 (`AL-409`).** The topology table's purpose column originally read
"state growth per loop" for `loop_and_grow` at every band, and the topology is named for
growth. At `3-5` and `5-8` the Tier-1 contract forbids the variables that would represent
growth, so an author was told twice by the name and the purpose column to accumulate
something, and once by the band table that the mechanism did not exist. That is not a
theoretical tension: of the six `loop_and_grow` skeletons in the catalogue, all at `3-5` or
`5-8` and all declaring no variables, no `on_enter` effects and no conditional choices,
**three produced prose asserting accumulated state that no path could establish**, including
one ending that counts "Three rescues by you" on a path containing one. The purpose column
above now names the two readings separately.

At `3-5` and `5-8`, a `loop_and_grow` hub is a **try-again** shape: the reader returns to the
same choice having learned something, and the prose at the hub and at every ending must read
correctly for a reader who took the loop once, twice, or not at all. Nothing may be counted,
collected, or referred back to as already-met. Authors who want accumulation want `8-11` or
above, where Tier 2 can carry it.

`sorting_hat` costs `sort + N x (track arc)` nodes, so it buys replay diversity at a node
premium and lives in Medium/Long cells, not Short; the table above annotates every band
where it appears accordingly.

#### Clarification (2026-07-27): reconvergence and endings

Earlier drafts of this ADR described endings as coming from "reconvergent leaves." A
measurement of the shipped skeleton corpus (61 skeletons) corrected that wording, and
this note records the finding, how it lines up against the JHM "essentially a tree (max
indegree 1.5)" anchor above, and the resulting enforcement stance.

- **The JHM figure is a mean of per-book maxima, and we exceed it.** JHM's "max indegree
  1.5 (range 1-3)" is the mean across books of each book's most-reconverged page, not a
  hard ceiling. The like-for-like statistic on our corpus is the mean of each skeleton's
  own maximum indegree, and that is **7.79** (median 4, range 1-126); only **25 of 61**
  skeletons keep their busiest node inside JHM's 1-3 range. On that metric we do **not**
  match JHM: our hub nodes are markedly more reconverged than the classic books', driven
  by a handful of large `open_map` and bottleneck-heavy skeletons (the worst is a single
  126-parent hub). Averaged over all 11,438 nodes the corpus is still tree-like, mean
  indegree **1.17** (1.18 if the 58 indegree-0 roots are excluded), but that is a
  different aggregate than JHM's and cannot be read as agreement with it. Earlier drafts
  cited **1.21** here; that figure is not reproducible from the shipped corpus and is
  superseded by the measured 1.17.
- **Reconvergence is real but internal, not at endings.** 45 of 61 skeletons have at
  least one reconvergent node, concentrated at bottleneck/hub nodes (a `branch_and_bottleneck`
  is a bottleneck by construction). But **54 of 61 skeletons have every ending at indegree
  exactly 1**; only 7 have any reconvergent ending, at a max of 4 parents. Endings are
  single-parent terminals; the ~15-22% ending share is achieved by **breadth** (many
  terminals off a branchy spine), the same mechanism as the genre, not by folding paths
  into shared endings.
- **Topology governs reconvergence; there is no per-band magnitude gate.** The validator
  regulates reconvergence through PL-18 topology admissibility
  (`validator/topology.py`), which splits on cycles first: a cyclic graph admits exactly
  `loop_and_grow` and `open_map`, and an acyclic graph *with* reconvergence admits exactly
  `branch_and_bottleneck` and `gauntlet` (`sorting_hat` is excluded there because it
  forbids a cross-track bottleneck). An acyclic graph with no reconvergence at all is
  `time_cave`, plus `gauntlet` when it is a pure linear spine or `sorting_hat` when it
  branches; those are the pure-tree shapes. Note that `open_map` is
  admissible only for cyclic graphs, so a DAG labelled `open_map` fails PL-18 whether or
  not it reconverges. Kid bands lean on the pure-tree shapes. The per-band
  Reconvergence column above ("minimal / light / moderate") is an **authoring guideline**,
  not a gated magnitude. `BandProfile.reconvergence_ceiling` stays an intentionally optional
  calibration dial: it is `None` for every band today and is read only by the mutation
  operator, never by the validator gate. **Decision: keep it unset** unless a future
  calibration shows kid-band skeletons drifting toward un-genre-like hub indegrees.
- **Choices per decision (2-4 per the section 10 band column; 2-3 as originally written
  here) stays an authoring guideline, not a hard gate.** The PL-17
  endings and decision floors already gate the two properties JHM tied to reader
  satisfaction and sales; an outdegree ceiling is not added as a validator error. If
  kid-band stories begin emitting overwhelming choice fans, revisit as an advisory finding
  rather than a hard block.

### 8. Series (campaign continuity)

A `series` tag chains multiple books. **Invariant:** in any non-final book, every
successful-completion ending converges on the next book's single `series_entry_node`
(many endings -> one entry), with declared state carried across. Series metadata:
`series_id`, `book_index`, `series_entry_node`, the continuation flag, and the
state-export contract. The series is a **meta-skeleton** (books are nodes,
completion->entry links are edges); v1 is a linear chain. Each book independently passes
its own band/length/style/topology gate. Young/tier-1 bands get **episodic** series (no
state carry). Schema/validator now; series generation is a later phase.

> **Addendum: series retirement (added 2026-07-26, owner decision).** The invariant above creates a
> promise to the reader, and this addendum protects it on the way out as well as on the way in.
>
> **Normative rule: a non-final series book is never retired before its replacement ships in the same
> release.** `Reader.tsx` offers "Continue the series" on a satisfying ending of a non-final book. If
> book 2 is withdrawn or materially changed while a reader holds a satisfying ending in book 1, that
> offer goes quiet with no in-product account, after a teen may have spent hours in a 550-node book
> and earned carried state.
>
> Two consequences follow:
>
> 1. **The replacement must accept the predecessor's carried state.** It is not enough for the new
>    book to pass its own gate; every satisfying-ending state of book N must be an admissible entry
>    state for the replacement book N+1. This is what validator rule `SR-9` gates.
> 2. **If it cannot, re-cut the predecessor to `is_final`** so the continuation is never promised in
>    the first place. Withdrawing the promise is acceptable; leaving it dangling is not.
>
> This binds the catalog-disposition principle (retire and replace rather than carry substandard
> work, recorded in [story-diversity-plan-v2.md](../story-diversity-plan-v2.md) section 6): the
> principle says a substandard book may be replaced, and this addendum says a non-final series book
> may not be replaced *alone*. The two are compatible; the series is the unit of replacement.
>
> Adopted as a written rule while the catalog has one author and one test household, because it costs
> nothing now and prevents a habit forming. Enforcement becomes live with the first reader outside
> that household.

### 9. Provenance

Cells are tagged by evidence: `8-11` measured (high); `5-8` node counts measured, rest
estimated; `10-13` medium; `13-16` gamebook metadata; `3-5`/`16+` product-defined. This
records which numbers are empirical and which are tunable product choices.

### 10. Amendment (2026-08-01): per-band choice grammar

> Adopted 2026-08-01 on owner sign-off, recorded as decision D15 in
> [design-review-kid-appeal-2026-08-01.md](../design-review-kid-appeal-2026-08-01.md) section 8.
> Companion to [ADR-026](./adr-026-rendered-stop-flow.md) (rendered-stop flow), which supplies the
> "stop" concept: one rendered page the child lands on, a flowed multi-node passage at `8-11` and
> up, a single node page at `3-5`/`5-8`. Applies to **new** skeletons and fills; the existing
> catalog is grandfathered and retired per cell under decision D11.

| Band | Presentation | Choice cadence | Max choiceless stops in a row | Flavor vs consequential | Options per choice | Words per stop |
| --- | --- | --- | ---: | --- | --- | --- |
| 3-5 | discrete pages | choice every 2nd-4th page; scaffold interaction (predict, point, answer) on other pages | 2-3 | ~90/10; consequences immediate, visible on the next page; reconvergence free | 2 | 10-55 |
| 5-8 | discrete pages | choice every 1st-2nd page | 2 | ~70/30; same-scene payoff | 2-3 | 30-95 |
| 8-11 | flowed prose | every stop ends in a choice | 1, prefer 0 | ~50/50; state-gated consequences begin, with a visible "noticed" cue | 3 | 60-135 |
| 10-13 | flowed prose | every stop ends in a choice | 0-1 | ~40/60; delayed, cross-scene consequences; distinct targets | 3 | 80-150 |
| 13-16 | flowed prose | every stop ends in a choice | 0-1 | ~30/70; consequence foreshadowed | 3-4 | 100-200 |
| 16+ | flowed prose | every stop ends in a choice | 0-1 | ~30/70; gamebook lethality per the section 5 shape | 3-4 | 100-230 |

Cross-cutting rules, all bands:

- **Every choice is acknowledged in the immediately following prose.** This is a fill-gate rule;
  the evidence base (Fendt et al. 2012, ICIDS; see the design review's research appendix) shows
  flavor choices sustain felt agency only when the next line visibly registers the pick.
- **Every interaction is story-congruent; none is decorative** (Takacs, Swart and Bus 2015).
- From `8-11` up, design for replay detection of reconvergence: differing acknowledgment lines,
  visible state.
- **Scaffold interactions** at `3-5` (predict/answer beats that are not plot forks) are the
  approved mechanism for choiceless pages; they require a schema minor (ADR-025) and their own
  small design before authoring uses them.

Relationship to section 6 (corrected 2026-08-22): this grammar is an **input** to section 6's
derived decision windows, not independent of them. The paragraph originally here claimed the
section 6 constants were "unchanged" and that decisions per path stayed ~4-8; that claim did not
survive arithmetic. "Every stop ends in a choice" plus the words-per-stop caps force more than 8
decisions onto the fastest finish in every Long cell and every `13-16`/`16+` cell, and this
table's options-per-choice column (3-4) always exceeded section 6's old "2-3". Section 6 as
amended now derives its windows from this table. The grammar itself governs surface pacing,
flavor mix, and per-stop reading load; the words-per-stop column is the operative *felt page
size* where stops flow (`8-11`+).

**Precedence between section 3 and this table (added 2026-08-22)**: the section 3 per-node hard
max is the hard gate; words-per-stop is the advisory felt-page target a stop should usually
meet, and a single large node may exceed it up to the section 3 max. At the page bands, where
one stop is one node (ADR-026), the words-per-stop upper bounds are set to the section 3
advisory maxima (`3-5`: 55, `5-8`: 95; originally 40 and 70, which pinned the mandated story
mean to the cap and made the advisory band's upper half unusable).

Enforcement lands as
validator rules for new content (choiceless-run caps at the graph level for the discrete-page
bands, acknowledgment checks at the fill gate); specifics belong to the implementation plan.

### 11. Amendment (2026-08-22): derived decision windows and column recalibration (`UW-C323`)

Adopted on the owner ruling of 2026-08-21 ("the 4-8 constant seems out of line with the
rest of ADR-011, especially sections 4 and 5"; recorded in
[live-structural-round-2026-08-21.md](../live-structural-round-2026-08-21.md) section
9.1) and the commissioned internal-consistency audit,
[adr-011-consistency-audit-2026-08-21.md](../adr-011-consistency-audit-2026-08-21.md),
whose findings this amendment implements in full. The audit showed section 6's flat
"~4-8 decisions per path, research-locked, all cells":

- arithmetically unsatisfiable in 10 of 18 production cells against this ADR's own
  sections 3, 5 and 10 (the fastest finish alone is word-forced above 8 decisions);
- flatly unsatisfiable for every gamebook cell (under 4-8 a gauntlet caps at <= 17
  terminals against envelopes implying 92-205);
- unsatisfiable as a floor at `3-5` Short, three independent ways;
- violated by the committed catalog in both directions (43 of 60 acyclic production
  skeletons above 8 max decisions per path, 16 of 81 below 4 on the fastest satisfying
  path), with the validator's own PL-17 breadth floor (0.08 x N) mathematically forcing
  large gauntlets to break it.

The root cause (audit item 9) was provenance overreach: a JHM measurement of
~90-120-node middle-grade books was declared "research-locked" across cells whose
`min->complete` runs 6 to 37 nodes, conflating path length with decision count in
exactly the way the research reconciliation warns against. The amendment re-anchors the
quantity the way every other quantity in this ADR is anchored: by derivation from the
word budgets.

What changed, mapped to the audit's amendment set (items 1-10):

1. **Section 6 rewritten**: decisions per path is a derived per-cell window (flowed
   bands: word-forced lower edge, arc-ceiling upper edge; page bands: cadence-derived
   with PL-17's `min_decisions` as floor); "~4-8" survives only as the JHM anchor.
2. **Gamebook cells exempted**: spine-scale decisions stated from catalog measurement;
   PL-17's breadth floor is the operative quantity.
3. **`3-5`/`5-8` floors** lowered to the enforced `band_profile` minima (1 and 2).
4. **Section 5 young-band endings ceilings** recalibrated upward against the committed
   strict-bar shelf (Short `3-5` 4 -> 8, Medium `3-5` 6 -> 18, Short `5-8` 10 -> 16,
   Medium `5-8` 16 -> 20).
5. **Section 5 gamebook preamble** now states the ruled >= 12% terminal floor and the
   two shipped regimes, replacing the stale 25-35% assertion.
6. **The "prose ~15-22%" endings fraction** demoted to a corpus-level descriptive
   figure; the section 5 per-cell columns govern (`_CELL_ENDING_BOUNDS`, `UW-C283`).
7. **Choices per decision** widened to 2-4 per the section 10 band column; section 10's
   false "unchanged" claim corrected in place.
8. **Sections 3 vs 10 precedence rule** added (per-node max is the hard gate); page-band
   words-per-stop caps raised to the section 3 advisory maxima (40 -> 55, 70 -> 95).
9. **Section 1a** MVP waiver extended to the decision windows.
10. **Section 5's missing `13-16`/`16+` Short rows** stated as deliberate.

Companion code change in the same commit: `band_profile.py::_CELL_ENDING_BOUNDS`
young-band rows recalibrated to item 4 (the ceiling is advisory; no committed skeleton
changes gate verdict, and the seven skeletons the old columns flagged are absorbed).
Deliberately **not** changed here: the M4 mutation operator still self-enforces the
historical 4-8 window as a no-worsen guard; re-deriving M4's guard per cell is tracked
as `UW-C326` in the unscheduled work register.

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
- [`docs/planning/research/`](../research/README.md): the empirical anchors (JHM 2019 + four-source
  reconciliation). **Citation resolved (2026-08-03)**; it was flagged stale on 2026-08-01 when the
  directory did not exist. The base was rebuilt from primary sources on 2026-08-02, and the
  four-source reconciliation itself was recovered and committed on 2026-08-03 as
  [cyoa-research-reconciliation.md](../research/cyoa-research-reconciliation.md). Read that note with
  its dated status notes: it predates this ADR, and several of its "net deltas to the project
  parameters" were overtaken by what shipped. See design-review-kid-appeal-2026-08-01.md section 6
  item 5 for the original flag.
- [ADR-026](./adr-026-rendered-stop-flow.md): rendered-stop flow (companion to section 10).
