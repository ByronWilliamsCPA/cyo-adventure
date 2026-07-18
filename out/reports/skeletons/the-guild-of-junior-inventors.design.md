# Design report: the-guild-of-junior-inventors

- **Cell**: 8-11 / long / prose (brief #13, Wave 5)
- **Topology / tier**: sorting_hat / 1
- **Designer model**: fable (initial design + 1 STRUCTURAL repair cycle)
- **Reviewer model**: opus (initial review + delta re-review, both with programmatic graph verification)
- **Disposition**: APPROVED for the fill stage

## Scripted validation (final)

```text
stats: nodes=191 endings=34 fill_nodes=191 cell=(8-11, long, prose) topology=sorting_hat tier=1
ok: skeleton passes gate and brief checks
```

Words 84-124 (mean 99.4); shortest satisfying completion 20 nodes (floor 14);
full-path decisions 4-6; pure tree with exact track isolation.

## The structural-monotony finding (the run's most instructive review catch)

The initial design instantiated ONE 64-node wiring shape three times
(identical decision suffixes, branch factors, path lengths, and positionally
identical ending roles across GEARS/GLIDERS/GADGETS, plus the same
"rush vs careful" dilemma cloned at the same depth). Every deterministic
check passed; only the independent reviewer, tracing shapes across tracks,
saw that a replaying reader would hit the identical rhythm re-skinned,
defeating the sorting_hat's core replay promise. Verdict: REVISE.

## Structural repair (verified exact in the delta re-review)

- GEARS kept as baseline: depths [4,8,8,11,11,11,12,15,16,19], lengths
  {13,14,15,18,21}, dilemma "rush vs temper".
- GLIDERS rewired: depths [4,7,9,10,10,12,13,14,17,18], lengths
  {12,13,14,16,17,19,20,21}, dilemma retyped "solo glory vs crew".
- GADGETS re-topologized: 57 nodes, 10 endings, 8 decisions (7 binary + 1
  ternary), max 5 decisions/path, ending roles moved at 8 of 10 positions,
  dilemma "scale up vs polish", one long earned honest-success chain.
- Pairwise wiring non-isomorphic on all three pairs (programmatically
  verified); completions cluster at different depths per track.

## Final verdict

Category 3 PASS; all regression axes clean (arcs, setback discipline,
anchors incl. the k3 permit fix, fillability of all edited beats).
OVERALL: APPROVE.

## Pattern rule added for all remaining sorting_hat briefs

Track BALANCE is not a goal; replay-rhythm DIFFERENCE is. Tracks should
differ in decision positions, path-length profiles, ending-role placement,
and dilemma type/depth. Unequal track sizes are fine. (Already propagated
to the envoy designer's brief.)
