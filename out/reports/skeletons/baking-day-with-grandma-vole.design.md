# Design report: baking-day-with-grandma-vole

- **Cell**: 3-5 / medium / prose (brief #4, Wave 5)
- **Topology / tier**: loop_and_grow / 1
- **Designer model**: fable (single pass, no repair cycles)
- **Reviewer model**: opus (independent, fresh context)
- **Disposition**: APPROVED for the fill stage

## Scripted validation (check_skeleton.py)

```text
stats: nodes=30 endings=6 fill_nodes=30 cell=(3-5, medium, prose) topology=loop_and_grow tier=1
ok: skeleton passes gate and brief checks
```

First-run pass; supervisor re-verification identical. Words hints 36-44
(mean 40.5) inside the 28-55 advisory.

## Structure summary

Linear recipe spine (`n_start` through `n_shape`) with four local cozy retry
loops (bowls, flour, two-node acorn chase, oven peek duplicated per track),
splitting after shaping into neat/funny flavor tracks that never reconverge;
3 positive endings per track (6 total, no negatives). Fastest satisfying
path 16 nodes (floor 7). Reviewer-verified: all 29 choice targets resolve,
all endings reachable, loop exits always available.

## Review verdict (7 categories)

1. Arc quality: PASS (acorn throughline and dough-nap story beat make it a
   ritual with anticipation, not a checklist)
2. Choice meaningfulness: PASS, flagged as the weakest dimension: 6 decisions
   per playthrough with four same-shape careful-vs-eager binaries in a row;
   judged at the upper edge of preschool tolerance but still fun because each
   mishap payoff is distinct
3. Loop soundness: PASS (never failure-shaming; no infinite-trap feel)
4. Reconvergence readability: PASS, with a stateless wrinkle to manage at
   fill time (see guardrails)
5. Band policy fit: PASS with one fill constraint (oven peeks)
6. Fillability: PASS
7. Diversity: PASS (genuine third loop_and_grow experience vs teddy picnic's
   hub-gather and star's climax funnel)

OVERALL: APPROVE. Optional non-blocking trim suggestion recorded: converting
one retry decision (flour or an oven peek) into a non-decision beat would
drop to 5 decisions and soften the binary repetition; deferred as a product
call since it would be a structural change to an approved skeleton.

## Notes for the future fill stage (guardrails)

1. `n_oven` / `n_oven_funny` peeks: keep Grandma clearly supervising; never
   depict Pip touching a hot surface or reaching toward heat; the mishap is
   heat escaping and buns slumping, nothing more.
2. Do not narrate the flour crock or seed jar emptying during the oops loops,
   so the loop-return stations ("crock full to the brim", "acorn on top")
   stay consistent without state.
