# Design report: the-smugglers-cut

- **Cell**: 13-16 / medium / gamebook (brief #24, Wave 5)
- **Topology / tier**: branch_and_bottleneck / 1
- **Designer model**: opus (Fable rate-limited; gamebook batch on Opus; zero repair cycles)
- **Reviewer model**: opus (independent networkx traversal from an isolated dir; audited all 14 lethal endings, not just a sample)
- **Disposition**: APPROVED for the fill stage (no fixes; one pacing/richness note)

## Scripted validation

```text
stats: nodes=277 endings=80 fill_nodes=277 cell=(13-16, medium, gamebook) topology=branch_and_bottleneck tier=1
ok: skeleton passes gate and brief checks
```

Reviewer confirmed: acyclic (zero cycles), admissible topology includes
branch_and_bottleneck, 10 reconvergence bottlenecks, no truncated titles, no
em-dash, all 277 nodes `<<FILL>>` with word hints 52-90 (13-16 gamebook
envelope).

## Structure summary

A night canal-city heist: a shared spine (approach -> water-gate -> yard ->
counting-hall -> the vault bottleneck -> escape -> canal junction -> the
boat) with branching route choices that reconverge at the key bottlenecks;
wrong choices split into fail terminals. 3 wins (clean take / take-with-a-cost
/ walk-away-alive), all off the `boat` node reached via the full spine.

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Topology + acyclic**: verified; bottlenecks yard=4, hall=3, junction=3,
  boat=3, g_vault=2; dominator-verified spine (hall -> g_vault -> boat), not
  a tree.
- **Floor (PL-20)**: all 3 wins at 26 nodes (>= 24); no satisfying leaf
  shallower.
- **Fair lethality (all 14 audited)**: every death/capture is a legible
  violation of a danger stated in its parent choice node; deaths grave,
  terse, gore-free.
- **Vault dominator/leak: clean.** g_vault is entry-agnostic ("nothing of
  the room behind you or the way you came"); hall dominates it so any shared
  reference is legitimate; no route-specific leak into the vault or the
  escape hub.
- **Ratios**: 80/277 = 28.9% terminals; 3 wins / 77 fails (7 death + 7
  capture + 63 non-fatal setback).

## Judgment note (reviewer endorsed)

The 63 non-fatal maze dead-ends are deliberately NOT lethal: all 14 lethal
outcomes sit on the telegraphed core-spine gambles, so death only ever
follows a knowingly-taken stated risk, never a blind maze wrong-turn. The
reviewer judged this a strength (legible, fair stakes discipline for 13-16),
not a weakness. The only note is a pacing one: 63 atmospheric dead-ends risk
reading samey at fill time; the fill author should vary them.

## Notes for the future fill stage

Hold g_vault, junction, and boat strictly entry-agnostic (their beats already
self-police). Vary the maze dead-end prose so the bulk fails don't converge
on "the run is blown, you flee." Keep deaths terse and gore-free.
