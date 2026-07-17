# Initial story inventory: run status summary

Live status grid for the authoring run defined in
`docs/planning/story-inventory-initial-run.md`. Updated by the supervisor at
wave boundaries and major approvals.

## Stories (one per offered age x length combination, prose)

| Band | Length | Story | Author | Status |
| --- | --- | --- | --- | --- |
| 3-5 | short | the-clover-and-the-butterfly | haiku | **APPROVED** (1 repair cycle) |
| 3-5 | medium | the-teddy-bears-picnic | haiku | **APPROVED** (2 repair cycles) |
| 5-8 | short | the-lantern-festival | haiku | **APPROVED** (1 repair cycle) |
| 5-8 | medium | the-backyard-treasure-map | haiku -> opus | **APPROVED** (2 cycles + Opus voice rewrite + re-review) |
| 8-11 | short | the-cave-of-echoes | sonnet | **APPROVED** (1 repair cycle) |
| 8-11 | medium | the-sky-ship-stowaway | sonnet | **APPROVED** (1 repair cycle) |
| 8-11 | long | the-clockwork-menagerie | sonnet | Wave 3 (not started) |
| 10-13 | short | the-midnight-museum | sonnet | **APPROVED** (1 repair cycle) |
| 10-13 | medium | the-hollow-lighthouse | sonnet | filling (resumed after usage-limit pause) |
| 10-13 | long | the-mapmakers-island | sonnet | Wave 3 (not started) |
| 13-16 | medium | the-signal-in-the-static | sonnet | filling (resumed after usage-limit pause) |
| 13-16 | long | the-vanishing-orchard | sonnet | Wave 3 (not started) |
| 16+ | medium | the-last-train-north | sonnet | filling (resumed after usage-limit pause) |
| 16+ | long | the-salt-archive | sonnet | Wave 3 (not started) |

**7 of 14 approved.** Wave 4 (4 gamebook style variants) queued behind Wave 3.

## Wave 5 skeletons (2 new per production cell; 36 total)

| # | Skeleton | Cell | Topology/Tier | Status |
| -: | --- | --- | --- | --- |
| 1 | the-sleepy-little-star | 3-5 S | loop_and_grow/1 | **APPROVED** (0 repairs) |
| 2 | puddle-jumping-day | 3-5 S | time_cave/1 | **APPROVED** (0 repairs) |
| 3 | the-big-red-balloon | 3-5 M | time_cave/1 | **APPROVED** (0 repairs) |
| 4 | baking-day-with-grandma-vole | 3-5 M | loop_and_grow/1 | **APPROVED** (0 repairs) |
| 5 | the-school-garden-mystery | 5-8 S | open_map/1 | **APPROVED** (1 repair: recap leak) |
| 6 | the-snow-day-expedition | 5-8 S | time_cave/1 | **APPROVED** (0 repairs) |
| 7 | the-tide-pool-rescue | 5-8 M | loop_and_grow/1 | **APPROVED** (1 repair: snail gag, setback tone) |
| 8 | the-night-market | 5-8 M | open_map/1 | **APPROVED** (polish cycle) |
| 9 | the-robot-fair-sabotage | 8-11 S | branch_and_bottleneck/1 | **APPROVED** (polish cycle) |
| 10 | the-locked-carousel | 8-11 S | open_map/1 | **APPROVED** (1 repair: caravan re-entry) |
| 11 | the-storm-chasers-club | 8-11 M | sorting_hat/1 | **APPROVED** (polish cycle); pattern-setter |
| 12 | the-river-of-small-boats | 8-11 M | time_cave/1 | **APPROVED** (0 repairs) |
| 13 | the-guild-of-junior-inventors | 8-11 L | sorting_hat/1 | designing (resumed) |
| 14 | the-hundred-door-hotel | 8-11 L | open_map/1 | designing (resumed) |
| 15-36 | (briefs 15-36) | 10-13 through 16+ | per briefs doc | queued |

**12 of 36 approved.** Design pipeline metrics so far: 6 first-pass gate
passes out of 6 designers; reviewer findings concentrated in tier-1
reconvergence/statelessness (the recap-leak class) and honest content-flag
declaration; every repair converged in one cycle.

## Run-wide process rules discovered (enforced in later prompts)

1. FK tuning must vary sentence shape, never uniform shortening; a
   dedicated ending-grammar pass is mandatory (fragments concentrate at
   endings otherwise).
2. Haiku lean-fill: words=N hints are hard targets; expansion via sensory
   short sentences; PL-19 named in exit criteria.
3. Review the highest-weight convergence node hardest (sky-ship climax).
4. PL-18: sorting_hat requires a pure tree (zero reconvergence anywhere).
5. Open_map recap nodes may cite only path-universal facts; interior nodes
   with two doorways must be re-entry-safe.
6. Shelf quotas: 5-8 hub-and-spoke full (2); 8-11 time_cave tones full (2);
   next 8-11 short should avoid another old-machine reveal.
