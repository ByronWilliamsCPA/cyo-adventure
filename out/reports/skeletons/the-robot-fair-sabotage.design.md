# Design report: the-robot-fair-sabotage

- **Cell**: 8-11 / short / prose (brief #9, Wave 5)
- **Topology / tier**: branch_and_bottleneck / 1
- **Designer model**: fable (initial design + 1 polish cycle)
- **Reviewer model**: opus (independent, fresh context)
- **Disposition**: APPROVED for the fill stage (reviewer approved outright;
  the three non-blocking seam fixes were applied anyway before approval)

## Scripted validation (final)

```text
stats: nodes=74 endings=14 fill_nodes=74 cell=(8-11, short, prose) topology=branch_and_bottleneck tier=1
ok: skeleton passes gate and brief checks
```

Words hints 90-120 (mean 100.5) inside the 70-135 advisory. Longest path 22
of 23 allowed hops.

## Structure summary

Three-act school whodunit: morning clues (three quick-look routes merging at
`n_assembly`), three suspect lines (Marcus/Poppy/Okafor) merging at the
lockup discovery (`n_lockup -> n_herbie -> n_plan`), then act-3 lines fanning
into the demo (`n_demo`, in-degree 7). 14 endings (5 positive, 5 neutral,
4 negative; no death/capture). The culprit is Herbie, a 30-year-old demo
robot on a garbled "TIDY ALL BEN-" chore routine; all three child suspects
redeem kindly. Floor path 17 nodes (floor 9) ending on a bittersweet
negative-valence completion the reviewer judged fair.

## Review verdict (7 categories): all PASS, OVERALL APPROVE

Key judgments recorded:

- Fair-play verified: universal clues at `n_survey` (sorted-not-stolen,
  wax wheel loops) plus each route independently establishing
  "a machine moved inside after lockup" before the merge, so the reveal is
  earned on every route.
- The load-bearing Okafor-absence device VERIFIED on all three parents of
  `n_plan`.
- Blame endings (`e_blame`, `e_rumor`) model social cruelty WITH explicit
  correction; dignity preserved.
- Honest below-ceiling flags (none/mild/mild) endorsed.
- Shelf note: carousel and robot-fair both feature an old machine; the next
  8-11 brief avoids a third old-machine reveal.

## Polish cycle (applied post-approval, supervisor-verified)

1. `n_lockup`: Ben re-seated (jogs over from the Sparks bench) so `x1`'s
   "between the two of them" holds on every route.
2. `n_demo` privacy assertion neutralized ("answered at last") and
   `y_story` no longer pre-commits the principal to telling the story, so
   the reader's `f_story` choice keeps its weight.
3. `y_agree`: explicit Gizmo rebuild beat added so no route reaches the
   demo without repairs mentioned.

## Notes for the future fill stage

`n_demo` beats assert only facts true on all seven parents (Herbie at the
gym, Gizmo "ready enough"); keep fill prose inside that envelope. The
stencil-label clue is route-gated to the bins branch; do not recap it at
bottlenecks.
