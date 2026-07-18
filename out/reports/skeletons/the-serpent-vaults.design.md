# Design report: the-serpent-vaults

- **Cell**: 13-16 / long / gamebook (brief #28, Wave 5) — the 13-16 Long dagger CEILING-CHALLENGER (low-end sibling: #27 the-labyrinth-of-glass, ~383 nodes)
- **Topology / tier**: gauntlet / 2
- **Designer model**: opus (gamebook batch; 5 repair cycles, incl. one architectural depth redesign)
- **Reviewer model**: opus (independent; full uncapped 8,917-config walk, per-lock air-reachability audit, ending-body clustering)
- **Disposition**: APPROVED for the fill stage (two bounded prose fixes applied by the supervisor)

## Scripted validation (post-fix)

```text
stats: nodes=530 endings=172 fill_nodes=530 cell=(13-16, long, gamebook) topology=gauntlet tier=2
ok: skeleton passes gate and brief checks
```

Reviewer confirmed: acyclic (zero cycles), 33-checkpoint spine with 29
reconvergence bottlenecks, longest path 73 edges (under the 80 cap), floor 71
choices (>= 32), 8,917 reachable configs uncapped, zero choiceless states,
zero dead conditional branches. Post-fix: 172/172 distinct titles, 29/29
distinct `_cap` bodies, no em-dash.

## State machine (three axes)

- `air` 0-3 (survival; dec at the 4 deep-lock pushes needing air>=1, reset 3
  at 5 air bells; the air==0 drown lives only at the last lock c22).
- `keys` 0-3 (monotone inc at 3 seal chambers; opens the final door by count).
- `flooding` bool (set once by the survivable sluice shortcut; decides the
  low exit dry or drowned at the finale).

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **The air==0 dead-branch discipline (special weight): verified.** The walk
  confirms air==0 is genuinely UNREACHABLE at locks 1-3 (min air at c16 is 1)
  and reachable only at c22, so placing the drown branch only at c22 keeps the
  partition exact over reachable states with zero dead conditional branches.
- **Exact-partition**: exactly one conditional choice per reachable state at
  all 14 state gates; unconditional companions everywhere, no choiceless
  state.
- **Best-win exactness**: win_best reachable at exactly {keys:3, air:3,
  flooding:false}; the other 5 wins occupy disjoint state regions.
- **Fair lethality**: fatals legible, every Wait/Hold carries delay-is-death,
  deaths grave/terse/gore-free.

## Fixes applied (reviewer-recommended, both bounded prose)

1. **29 `_cap` capture bodies widened.** They shared one byte-identical FILL
   directive (no chamber token). Each now injects its chamber name (parsed
   from its already-distinct title), mirroring the per-chamber `_wait_e`
   pattern the designer used elsewhere; 29/29 bodies now diverge.
2. **Duplicate title resolved.** `c23_prop_e` and `c25_prop_e` both read
   "Propped and Fallen"; renamed to "The Slab Came Down" / "The Arch Came
   Down" (matching their slab vs arch crush hazards). Now 172/172 distinct.

## Dagger-experiment finding (the 530-node challenger)

- **Title-distinctness ceiling sits between 530 and 677.** This 530-node book
  held 171/172 distinct titles pre-fix (172/172 post-fix); the 677-node
  tenfold-siege collapsed to 46/209. So distinctness is comfortably
  sustainable at 530 and breaks (as an authoring economy) only past it.
- **Body prose proportionally CLEANER than the smaller cinder-bazaar.**
  Serpent-vaults' templating was ~33/172 (~19%) identical bodies (the 29 caps
  + 4 panic-drowns) BEFORE the fix, versus cinder-bazaar's 80/141 (~57%) at
  453 nodes; the 28 `_wait_e` deaths were each individually chamber-specific.
  So larger did not mean worse here.
- **The real scale cost was correctness architecture, not content.** The
  load-bearing repair (of 5) was structural: v1 blew depth to 96 > 80 because
  the degrade route added a 4th spine edge per checkpoint, forcing a full
  redesign to 2-hop shallow checkpoints so 33 fair checkpoints fit under the
  wall. This matches the tenfold-siege lesson: past the ceiling, the
  hand-authoring strain is in correctness/depth-legality reasoning (which the
  gate + config walk catch), not in the machine-checkable invariants.

## Notes for the future fill stage

Pin the final-door key logic (3 full / 2 half / 1 hand-width / 0 shut) and
the air-bell-before-every-lock rhythm. Write the 31 turn-back caps as the
survivable retreats they now are (chamber-specific), distinct from the deep
drown deaths.
