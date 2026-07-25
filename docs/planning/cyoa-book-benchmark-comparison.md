---
title: "Published CYOA/Gamebook Benchmark Comparison"
schema_type: common
status: draft
owner: core-maintainer
purpose: "Compares the Storybook schema/validator/condition-evaluator against structural mechanics used in real published choose-your-own-adventure and gamebooks, to surface strengths and gaps."
tags:
  - planning
  - storybook
  - validator
---

# Published CYOA/Gamebook Benchmark Comparison

This compares real, published interactive-fiction books against our Storybook
model (`storybook/models.py`), condition evaluator (`storybook/condition.py`,
`storybook/evaluator.py`), and topology validator (`validator/layer1.py`,
`validator/layer2.py`) to find structural strengths and gaps. It does not
reproduce any book's text; only its publicly-documented branching mechanics are
described, and the two benchmark fixtures built alongside this doc are
original content that model those mechanics, not excerpts.

## Framework capabilities used as the comparison baseline

- **State**: a flat list of globally-declared `Variable`s, `bool` or `int`
  only, `int` bounded to `[-1e9, 1e9]` with optional `min`/`max` (clamped at
  runtime by `player/engine.py`). No `str`/`float`/list/object state, no
  first-class inventory or stats subsystem, and no visited-node/history
  predicate. Tier-1 stories may declare no variables at all (pure static
  branching).
- **Conditions**: a 10-operator whitelisted JSONLogic-shaped evaluator
  (`var`, `!`, `and`, `or`, `==`, `!=`, `<`, `<=`, `>`, `>=`), deliberately
  hand-rolled (~40 lines) rather than a general expression language
  (ADR-006), to keep untrusted LLM-authored conditions safe to execute.
- **Effects**: `set`/`inc`/`dec` on a single declared variable by an
  author-fixed, non-negative integer literal. No randomness primitive exists
  anywhere in the schema.
- **Topology**: cycles are allowed (`loop_and_grow`, `open_map`), but any
  cycle that cannot reach an ending is a hard `L1-5`/`L2-10` failure. Every
  node and ending must be reachable from `start_node` (`L1-3`); an orphaned
  node, including an intentionally "secret" one, is a hard validation error,
  not a warning.
- **Endings**: typed on two closed enums only, `kind` (success / setback /
  death / capture / completion / discovery) x `valence` (positive / neutral /
  negative). No free-string ending category.

## Books used as test cases

| Book | Mechanic under test | Maps onto |
|---|---|---|
| *The Cave of Time* (Packard, CYOA #1) | Pure branching tree, no state, ~40 endings, many bad-but-survivable endings | Tier-1, `time_cave`/`gauntlet` topology |
| *Journey Under the Sea* (Montgomery, CYOA #2) | A piece of equipment bought early gates survival on a later branch | Tier-2, single bool `Variable` + `Condition` gate (already covered by the repo's own `03_tier2_lantern.json` fixture) |
| *The Lost Jewels of Nabooti* (Montgomery, CYOA #4) | Jewels collected across independent branches; the *count* recovered by the end determines which of several endings is reached | Tier-2, int accumulator + threshold conditions at a reconvergence node: **new benchmark fixture 1** |
| *Inside UFO 54-40* (Packard, CYOA #13) | A repeatable loop around the ship; a "secret" ending advertised on the back cover that is reachable only by disobeying the book's page-turn instructions, not through any listed choice | `loop_and_grow` topology; the secret ending itself is the interesting case: **new benchmark fixture 2**, with a caveat (see below) |
| *The Warlock of Firetop Mountain* (Jackson & Livingstone, Fighting Fantasy #1) | Rolled stats (Skill/Stamina/Luck), dice-resolved combat, an inventory of items/gold/provisions | Stresses the framework's numeric-state ceiling and its total absence of randomness |
| *Flight from the Dark* (Dever, Lone Wolf #1) | Player picks N "Kai Disciplines" from a list at character creation; a capacity-limited backpack; Combat-Skill-ratio combat via a Random Number Table | Stresses "player-authored initial state" and inventory-capacity constraints |

## Findings

### Strengths confirmed by the comparison

1. **The Cave of Time's shape is a non-issue.** A large acyclic tree with many
   terminal endings of mixed valence is exactly what Tier-1 (no variables)
   plus `time_cave`/`gauntlet` topology was built for; the existing catalog
   already carries skeletons at this scale (e.g. *The Pale Road*, 498 nodes,
   147 negative endings) without strain.
2. **Journey Under the Sea's item-gate is already a solved case.** A single
   bool `Variable` set on pickup and checked with `==` at a later choice is
   precisely `tests/fixtures/storybook/valid/03_tier2_lantern.json` in this
   repo today.
3. **The Lost Jewels of Nabooti's count-based branching is expressible
   cleanly.** An `int` variable with `min`/`max` bounds, incremented by fixed
   amounts across independent branches, and read by `>=`/`==` thresholds at a
   reconvergence node, validates without any framework changes; see
   benchmark fixture 1 below. The runtime clamp on bounded ints means the
   author does not have to hand-guard against overflow.
4. **UFO 54-40's repeatable-loop-unlocks-content pattern is directly
   supported.** `loop_and_grow` plus an incrementing loop counter that gates
   a bonus node once a threshold is crossed is exactly what
   `validator/layer2.py`'s stateful reachability checks (`L2-9`/`L2-10`/`L2-11`)
   are designed to admit and verify; see benchmark fixture 2.
5. **The hard reachability/no-dead-content guarantee (L1-3) is a genuine
   strength, not just a constraint.** None of the six books above could ship
   an unreachable node or a trap loop with no escape under our gate; that
   class of authoring bug (a broken branch nobody notices until a reader
   hits it) is caught at validation time, before a human reviewer or a child
   reader ever sees it.

### Gaps surfaced by the comparison

1. **UFO 54-40's actual secret ending is inexpressible by design, not by
   oversight.** The real mechanic's whole point is that the ending is *not*
   reachable via the book's advertised choice structure: you find it only by
   breaking the rules of navigation. Our `L1-3` reachability check has no
   concept of "reachable by disobeying the graph"; an ending with no
   satisfiable incoming choice is a hard validation failure. Benchmark
   fixture 2 therefore models the closest *expressible* analogue (a
   loop-count-gated bonus room, reachable but not obvious on a first pass)
   rather than a literal port. This is worth naming explicitly: the framework
   cannot and should not represent "content only reachable by breaking the
   reader interface", which is consistent with ADR "mandatory human approval"
   and the reachability guarantee, but it is a real, permanent expressiveness
   ceiling relative to at least one well-known published mechanic.
2. **No randomness primitive at all.** Fighting Fantasy and Lone Wolf combat
   is fundamentally dice-resolved; our `Effect` model only supports
   author-fixed literal `inc`/`dec` amounts, never a random draw. A
   dice-driven combat system can only be approximated by pre-branching every
   outcome the author is willing to write by hand (an "if you rolled high"
   / "if you rolled low" choice pair authored as two fixed branches), which
   defeats the compactness dice give a real gamebook and would blow up node
   counts fast for anything beyond a single combat round. This is a
   deliberate simplicity trade-off per ADR-001/ADR-006, not a bug, but it is
   the sharpest ceiling this comparison found. ADR-006 already names CEL as
   "a future escape hatch, not v1": a bounded, whitelisted random-effect
   operator (e.g. a `roll` op with a fixed die and a declared seed policy)
   would be the natural place to extend if stat/dice gamebooks are ever a
   target genre.
3. **No first-class inventory or stats block.** Skill/Stamina/Luck or a
   backpack of items must each be hand-declared as an individual `int`/`bool`
   `Variable`; there is no "this story has an inventory of up to N item
   slots" primitive. This is workable (as fixture 1 shows for two items) but
   scales awkwardly: Lone Wolf's several dozen possible inventory items would
   mean several dozen individually-declared bool variables, each condition
   and effect referencing them by hand, with no automatic capacity
   enforcement: capacity has to be separately modeled as its own `int`
   counter, checked in every acquisition choice's condition.
4. **No player-authored initial state.** Lone Wolf's character-creation step
   (pick N Kai Disciplines from a list before node 1) has no direct schema
   equivalent: `Variable.initial` is a single author-fixed value, not a
   player choice made before the story starts. It is emulable as an opening
   sequence of nodes/choices that each `set` a different variable, but that
   is a hand-rolled workaround, not a modeled concept, and it consumes real
   node budget for something that in the original book is a single
   character sheet, not part of the narrative graph.
5. **No "visited node before" predicate.** None of the six books strictly
   required it to model here, but several gamebook traditions (and some of
   our own `open_map`/`sorting_hat` skeletons) would benefit from a condition
   like "you have already been to node X" without the author manually
   threading a dedicated bool variable through every relevant node's
   `on_enter` effects. Currently that has to be hand-authored per story.

## Benchmark fixtures built

Two new schema-valid, non-production (`production_eligible: false`) skeleton
shells were added under `tests/fixtures/storybook/benchmarks/` (deliberately
kept out of `skeletons/`, which is `rglob`-scanned by
`scripts/render_skeleton_diagrams.py` into the production catalog table; these
are benchmark test cases, not catalog entries). Both validate cleanly through
the full gate:

```bash
uv run python scripts/check_skeleton.py \
  tests/fixtures/storybook/benchmarks/benchmark_item_accumulation_salvage.json \
  --allow-mvp --band 8-11 --tier 2 --topology branch_and_bottleneck

uv run python scripts/check_skeleton.py \
  tests/fixtures/storybook/benchmarks/benchmark_loop_and_grow_secret_room.json \
  --allow-mvp --band 8-11 --tier 2 --topology loop_and_grow
```

- **`benchmark_item_accumulation_salvage.json`** (9 nodes, 4 endings):
  models *The Lost Jewels of Nabooti*'s collect-and-count mechanic. A bool
  `has_light` gates a second item pickup; an int `jewel_count` (bounded
  0-2, clamped by the runtime) accumulates across two independent dive
  branches; a reconvergence node routes to one of three endings by exhaustive
  `jewel_count` threshold (`>=2` / `==1` / `==0`).
- **`benchmark_loop_and_grow_secret_room.json`** (6 nodes, 3 endings):
  models *Inside UFO 54-40*'s repeatable-loop structure. An int `loop_count`
  increments each round trip through a corridor/bridge cycle (always
  escapable, so no trap loop); a bonus discovery ending unlocks only once
  `loop_count >= 2`. As noted above, this is the closest expressible
  analogue to the real book's secret-ending gimmick, not a literal port:
  the real mechanic's "unreachable via the choice graph" property is exactly
  what our `L1-3` reachability rule forbids.

## Recommendation

No schema/validator changes are proposed here: every gap above (randomness,
inventory-as-primitive, player-authored initial state, visited-node
predicates) is a known, bounded expressiveness trade-off already reasoned
about in ADR-001/ADR-006, not a defect. If a future roadmap phase wants to
target dice-driven or inventory-heavy gamebook styles (there is already a
`narrative_style: gamebook` metadata field for 13-16/16+ bands), the concrete
next step would be a new ADR proposing a narrow, whitelisted extension (a
bounded `roll` effect operator, and/or a `visited(node_id)` condition
primitive) rather than opening up the condition evaluator to a general
expression language.
