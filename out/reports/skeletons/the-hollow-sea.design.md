# Design report: the-hollow-sea

- **Cell**: 13-16 / long / prose (brief #26, Wave 5)
- **Topology / tier**: open_map / 2 (largest tier-2 open_map yet at 197 nodes)
- **Designer model**: opus (Fable rate-limited; batch moved to Opus at the user's direction; zero repair cycles)
- **Reviewer model**: opus (independent; drove the real StoryEngine via walk_configurations, reproduced the full 15,510-config closure and every gate claim)
- **Disposition**: APPROVED for the fill stage (no fixes required; one fill-stage note on the thin floor margin)

## Scripted validation

```text
stats: nodes=197 endings=40 fill_nodes=197 cell=(13-16, long, prose) topology=open_map tier=2
ok: skeleton passes gate and brief checks
```

Layer-2 walk: 15,510 reachable configurations, capped=False (complete
enumeration), all 40 endings reachable, zero blocking findings. Words/node
126-175. No em-dash; no truncated ending titles (supervisor scan).

## State machine (three axes)

- `soundings` 0-2 (monotone progress clock; +1 once-per-reach at the six
  `_done` nodes; zero dec effects; IS the clock the sea mutates under).
- `supplies` 0-3 (capability; reset to 3 at hub and muster; dec 2 at four
  reach detours).
- `hull` bool (condition; reset true at hub and muster; false at two
  hazards).

Reviewer confirmed ranges hold, soundings is strictly monotone, and the six
reaches split cleanly (4 supply-detour + 2 hull-hazard).

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Base-plus-adds (the tier-2 open_map contract): clean.** Across all
  15,510 reachable configs, zero choiceless non-ending states; the set of
  gated nodes is exactly the nine named, each with a verified unconditional
  companion.
- **Best-outcome exactness: verified.** The sea's fullest "answer" chain
  (six nodes) is reachable only at soundings==2; honest completions are
  reachable at soundings 0/1/2, so a satisfying ending is always available.
- **Re-entry safety: verified.** Hub and muster both reset supplies=3 /
  hull=true; enumeration confirmed zero cross-reach hops, so laden/holed
  entry into any reach is structurally impossible (the flooded-quarter
  `laden` pattern).
- **Leak/dominator: clean.** fin_tide (in-degree 3, three prep-jobs merge)
  names all three outcomes symmetrically ("all three were seen to by many
  hands") and never surfaces which job the reader chose; hub and muster
  cite only path-universal facts.
- **Band fit**: no death, no capture endings (awe-over-terror register
  held); peril nodes carry safety_scope; scariness/peril=intense within the
  16+... i.e. 13-16 ceiling.

## Fill-stage note (reviewer-flagged, no fix)

The satisfying-completion floor is exactly 21 nodes against a floor of 20:
correct today, but any future edit that trims a node from the
muster-to-finale spine would drop it under the floor. Do not shorten that
spine at fill time.

## Notes for the future fill stage

Pin the fact sheet (the Hollow swallows sound; Wren/Mabe/Fen aboard
Kestrel; the six reaches and their hazards; the Stilling answers only a
boat that has read its reaches). Hold fin_tide, the hub, and the muster
strictly arrival-neutral. Keep the silence written as awe, not fear.
