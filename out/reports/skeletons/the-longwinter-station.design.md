# Design report: the-longwinter-station

- **Cell**: 16+ / long / prose (brief #34, Wave 5)
- **Topology / tier**: open_map / 2 (largest tier-2 open_map of the run at 248 nodes; first with a persistent cross-spoke trust ledger)
- **Designer model**: opus (Fable rate-limited; batch on Opus at the user's direction; zero repair cycles)
- **Reviewer model**: opus (independent; drove the real StoryEngine, reproduced the full 51,241-config closure and every gate/floor claim)
- **Disposition**: APPROVED for the fill stage (no fixes; one cosmetic self-report label note)

## Scripted validation

```text
stats: nodes=248 endings=44 fill_nodes=248 cell=(16+, long, prose) topology=open_map tier=2
ok: skeleton passes gate and brief checks
```

Layer-2 walk: 51,241 reachable configurations, capped=False (complete
uncapped enumeration), all 44 endings reachable, zero blocking findings.
Words/node 162-202. No em-dash; no truncated ending titles.

## State machine (three axes, one persistent)

- `deepcold` 0-2 (monotone progress clock; +1 once-per-module at the six
  `*_done` nodes; read only at the finale `fin_still`).
- `fuel` 0-3 (rationed heat; reset to 3 at hub `n_mess` and `fin_muster`;
  dec 2 at four module detour choices; read by four fuel gates).
- `trust` 0-2 (crew cohesion; PERSISTS, never reset; inc/dec at the six
  `*_call` choice-pairs and two crew-module decs; read by two trust gates
  and, with deepcold, by the finale best gate).

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Base-plus-adds with persistent trust (the hardest case): clean.** Zero
  choiceless non-ending states across all 51,241 configs. The critical
  case holds: trust==0 arrivals occur at both trust gates and each keeps an
  unconditional read-alone companion, so persistence never strands a
  reader.
- **Gates genuinely bite**: every gate has both open and closed reachable
  arrivals (fuel {1,3}, trust {0,1,2}); none is always-true.
- **Best-outcome exactness: verified.** fin_read is reachable at exactly
  (deepcold=2, fuel=3, trust=2); no leak outside {deepcold==2, trust==2};
  wins remain available at lower states.
- **Re-entry safety + floor**: hub and muster reset fuel; no spoke-to-spoke
  hops (only trust crosses boundaries); the designer's deliberate removal of
  any hub->muster shortcut yields a robust 32-node satisfying floor (>= 23).
- **Leak/dominator: clean.** n_mess (in-degree 8) and fin_ready (in-degree
  3, three prep tasks) are arrival-neutral; fin_ready states no
  prep-task-specific fact ("all three were seen to by the whole crew").
- **Band fit**: 6 death endings, all the cold taking someone who broke the
  buddy rule, authored "grave and cold and without gore"; awe-over-terror
  register held.

## Self-report note (cosmetic, no skeleton change)

The designer's report attributes the fuel/trust decs to `*_hard` choices;
the reviewer found they actually live on the `*_near` choices. The
mechanics are exactly as described; only the report's node label is wrong.

## Notes for the future fill stage

Pin the fact sheet (Sable Ice Shelf station layout; the five-crew roster
Kerr/Halvard/Ivo/Marta/Sunny; the buddy rule and heat-is-life rule; the
signal kept ambiguous and never explained). Hold n_mess, fin_muster, and
fin_ready strictly arrival-neutral. Keep trust as the winter's running
ledger of crew cohesion; keep the signal awe, not answer.
