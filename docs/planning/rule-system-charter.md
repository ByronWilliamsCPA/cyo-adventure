# Giving future stories the best chance: what to add, remove and change

Written 2026-08-18, from the seven-lane audit, five story-first drafts, and Waves 0 to 4 of
remediation. Grounded in measurements taken during that work; every number here was run, not
recalled.

## The diagnosis, which decides everything below

The catalog of rules is roughly 50: PL-15 to PL-29, CG-1 to CG-4, L1-1 to L1-8, L2-9 to L2-14,
RL-13, SR-1 to SR-9, CH-1 to CH-8. Across about twenty audit findings and five authoring
experiments, **not one finding was "a story failed because a rule was missing."** Every one was:

| failure mode | instances |
| --- | --- |
| the rule could not fire at its entry point | 3 (CG-4, the M2 anti-clone floor, the R4 theme gate) |
| the rule counted a different unit than its source measured | 3 (PL-25, PL-26, CG-3) |
| the rule contradicted another rule | 5 (PL-17 vs ADR s5, PL-29 vs PL-18, PL-20 vs the walk floor, CG-4 vs reconvergence, the prompt vs PL-17) |
| the bound was never told to the generator | the largest single effect measured |

The one genuine gap, an endings CEILING, was named by the owner rather than found by the gate.

**So the answer is: add almost no rules. The system's failures are integration failures.** More rules
would add more surface for exactly the four modes above.

## The single highest-leverage change, by an order of magnitude

Tell the generator every bound it will be graded against. Measured, one-node-per-passage form:

| story-first draft | constraints stated? | blocking errors |
| --- | ---: | ---: |
| 5-8, 8-11, 10-13 | no | PL-19 across most nodes |
| 13-16 | no | **17** |
| 16+ | **yes** | **2** |

Median scene length across the four unbriefed drafts was 246, 439, 400, 279 words: no trend, so the
model does not infer a band's pacing. Told a 230-word bound it produced median 198, max 230, with
zero PL-19 and zero CG-3 findings.

Note the confound and that it runs the right way: 16+ has the LARGEST words-per-node budget in the
catalog and produced the SMALLEST median. If band drove scene length that run should have been the
longest.

**Make this structural, not a habit.** A test that every gated numeric bound appears in the rendered
prompt for its cell, generalising the 18-cell ending-count test added in Wave 2b. A bound the gate
enforces and the prompt omits is a defect by construction.

## ADD: two things, and neither is a rule

1. **A per-cell feasibility prover.** For each of the 18 offered cells, synthesize a minimal story
   satisfying every BLOCKING rule simultaneously; fail if none exists. This would have caught
   `UW-C272` (topologies offered but unbuildable in 15 of 18 cells), PL-17's floor exceeding its own
   ceiling in three cells, and the degenerate 3-5/short window, all before any of them reached an
   author. The PL-18/PL-29 feasibility test added in Wave 4 is the one-property prototype; this is
   the general form and it is the most valuable single thing left to build.
2. **The prompt-completeness test** described above.

Both are tests. Neither constrains a story.

## REMOVE: four things, none of them a rule's substance

1. **One property, three definitions.** "Satisfying" means ending KIND to PL-20, ending VALENCE to
   the strict walk floor, and both to PL-24. Catalog-wide that is 472 endings against 968, with 500
   satisfying one reading and not the other. Consolidate to a single named predicate that all three
   import, with the difference stated once if a difference is genuinely wanted. Do NOT resolve it by
   switching the walk floor to kind: that was tried and would make the teen gamebook cells
   unauthorable (`AL-460`).
2. **SAFE-14's phantom entry.** `validator-rules.md` lists it in the live application order;
   `validator/safety.py` returns an empty report and says so. Either implement it or take it out of
   the order. A catalogued rule that cannot fire is worse than no rule, because it reads as coverage.
3. **The flat prose density ceiling as a value.** After the Wave 3 per-band derivation,
   `_NODES_PER_DECISION_CEILING["prose"]` is reachable only as a fallback for an unconfigured band.
   Keep it as that fallback; stop describing it as the ceiling.
4. **`_ENDINGS_FRACTION` as the prose endings floor.** It is now capped by the cell bounds in every
   prose cell, so it binds only in the four gamebook cells the ADR gives no numbers for. Say that,
   rather than leaving two mechanisms that look co-equal.

## MODIFY: the tier, by a rule that already earned its keep

Waves 3 and 4 produced a decision procedure worth writing down, because the same test gave opposite
answers and both were right:

> **When a new bound fails committed content, check whether the newest deliberately compliant
> artifact passes it. Count alone cannot distinguish legacy debt from miscalibration.**

- PL-17's new endings ceiling failed 7 skeletons INCLUDING `the-last-blue-cup`, authored to the
  strict bar hours earlier. Shipped advisory.
- CG-3's new stop ceilings failed 186 nodes but `the-last-blue-cup` and `the-seedling-thief` sit
  EXACTLY at 40 and 70 with zero violations. Shipped blocking.

Two specific tier changes follow:

- **CG-4 should apply only where acknowledgment is possible.** Measured over 12 filled books, CG-4
  findings per node run 0.16 at in-degree 1, 0.55 at 2-3, and 1.56 at 4+. A hub with 15 parents
  cannot acknowledge 15 different choices, and `UW-C272` shows reconvergence is the only achievable
  shape above 3-5, so the gate pushes authors toward the shape CG-4 punishes. Restrict it to
  in-degree 1 rather than raising its threshold: at in-degree 1 it measures something real.
- **`UW-C288` needs no rule change at all.** It was filed as a three-way conflict between the stop
  bound, PL-25's floor and CG-1's allowance. It is not: ONE establishing node satisfies PL-25's node
  test outright at every band, and the stop bound still has room for it (8-11 needs establishing plus
  first decision inside 135 words, 16+ inside 230). The 16+ writer eliminated single-choice passages
  entirely because it was told the stop bound and NOT told the opening floor. Tell both. This is the
  first principle again, not a new constraint.

## The charter: what a new rule must carry

Every finding in this workstream would have been prevented by one of these, so make them entry
conditions rather than review comments:

1. **A stated unit.** What does the source measure, and does the code count that? Three rules failed
   this.
2. **A cited source and its scope.** Which bands, which cells, which corpus. PL-26 applied one
   corpus in one band cluster to all six bands.
3. **A can-fire test at its production entry point.** Not a direct call: all three dead rules fired
   when called directly and were dead in the wiring.
4. **A feasibility check against the rules it interacts with**, per cell.
5. **A tier chosen by the evidence test above**, not by how bad the violation sounds.
6. **A line in the rendered prompt**, so the generator is told what it will be judged on.

A rule that cannot supply all six is not ready, however obviously good it sounds.
