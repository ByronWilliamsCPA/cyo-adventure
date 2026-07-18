# Design report: the-red-meridian-run

- **Cell**: 16+ / medium / gamebook (brief #31, Wave 5) — the 16+ Medium dagger LOW-end skeleton
- **Topology / tier**: gauntlet / 1 — **the first gauntlet-topology skeleton in the project; pattern-setter for the five gauntlets that follow**
- **Designer model**: opus (Fable rate-limited; gamebook batch on Opus; 3 build iterations, checker passed first run of the sound v3 architecture)
- **Reviewer model**: opus (independent networkx traversal; verified acyclicity, spine indices, floor, and every sampled telegraph)
- **Disposition**: APPROVED for the fill stage (no skeleton edits; one propagation note folded into the gauntlet rule set)

## Scripted validation

```text
stats: nodes=306 endings=90 fill_nodes=306 cell=(16+, medium, gamebook) topology=gauntlet tier=1
ok: skeleton passes gate and brief checks
```

Reviewer confirmed: `is_directed_acyclic_graph` True (zero cycles),
`admissible_topologies` includes GAUNTLET, zero back-edges (every edge's
target has a spine index >= its source), all 90 ending titles unique and
untruncated, no em-dash, all 306 nodes carry `<<FILL>>` directives with
word hints in 56-92 (16+ gamebook envelope).

## Structure summary

A lethal blockade run across a contested strait: a spine of 13 sequential
checkpoints (harbor boom through the wire at the landing beach), each 3
spine nodes (approach / gate / pass). Wrong choices die in shallow off-spine
fail branches; a spotted-but-alive gamble at each checkpoint reconverges
FORWARD onto the next checkpoint. 3 deep wins gated behind the full spine.

## Review verdict (7 categories): all PASS, OVERALL SHIP, PATTERN SOUND

- **Gauntlet topology + acyclic (load-bearing): verified.** 13 reconvergence
  bottlenecks (each in-degree 2, fed by the prior checkpoint's pass + slip);
  restart-on-fail fully unrolled forward, no back-edge.
- **Floor (PL-20)**: all 3 wins are 47 nodes (>= 29); no satisfying leaf
  shallower.
- **Fair lethality**: every sampled fatal choice is a legible violation of a
  rule stated in its own gate body; no untieable death. The softest cases
  are the "Wait/Hold" fatals (lethality by inference); folded into the rule
  set as a "delay is death" fill note.
- **Ratios**: 90/306 = 29.4% terminals (>= 25% floor); 28 decisions (>= 8%
  floor); 3 wins / 87 fails (73 death + 14 capture); deaths grave, terse,
  gore-free.

## Confirmed GAUNTLET PATTERN RULE SET (established here; recorded in design-briefs.md)

The reviewer endorsed the structure as the pattern for briefs #23, #27,
#28, #35, #36, with one propagation refinement (item 5):

1. Acyclic, restart unrolled: never author a back-edge; a "retry" is a
   terminal fail or a distinct FORWARD node. Verify is_directed_acyclic_graph
   every build (a cycle reclassifies off gauntlet under PL-18).
2. One driving spine of checkpoints, kept shallow: each checkpoint ~3 spine
   nodes (approach/gate/pass); the win path sits in [min_complete_floor,
   cell max_depth]; put node BULK in off-spine fail branches, not a deeper
   spine, or the depth ceiling blows.
3. Reconvergence is the signature: route each spotted-survive/degrade branch
   FORWARD onto a later checkpoint's approach node so spine bottlenecks reach
   in-degree >= 2 (reconvergence >= 1 is what makes PL-18 admit gauntlet).
4. Fair lethality: state the danger/rule plainly in the gate body; every
   fatal choice is a legible violation of it; deaths are shallow (consequence
   beat -> dread beat -> terminal) but grave, terse, gore-free; use
   death/capture kinds freely at 13-16 and 16+.
5. **Prose-variety guard (reviewer refinement): do NOT let the dread beat
   collapse onto a tiny shared pool.** The pattern-setter used 4 dread
   directives across 72 dread nodes; for the following gauntlets, make each
   dread directive reference its checkpoint's specific hazard, and give the
   "Wait/Hold" consequence nodes an explicit "delay is death" beat.
6. Few deep wins, many shallow fails: ~25-35% terminals, only a handful
   wins, all gated behind the full spine so the shortest satisfying path
   clears the arc floor. Confirm endings >= ceil(0.25*nodes) and decisions
   >= ceil(0.08*nodes).
7. Terse gamebook prose: second person, punchy, words=N leaning 55-95 for
   16+ (45-80 for 13-16); every non-ending node a `<<FILL>>` directive.
8. Give each gate real breadth (6-7 choices: 1 correct + several telegraphed
   fatals + 1 gamble) so a 13-14 checkpoint spine carries ~90-105 endings
   without a runaway depth.
9. Co-located flavor wins are acceptable for a STATELESS (tier-1) gauntlet:
   with no state, clean/costly/quiet as a final-arrival split is the honest
   option; three genuinely distinct earned routes require tier-2 state.

## Baseline effort evidence (for the ceiling-challenger comparison)

3 build iterations (deep-spine v1 -> shallow-fan rewrite v2 -> node-count
tune v3); the official checker passed on the first run of v3; 2 defects
self-caught before the checker (a dangling target, and the v1 deep-spine
whose ~112-hop longest path would have failed the 73 depth ceiling). The
single most important build decision was catching the deep-spine depth
problem in design analysis rather than after a checker failure. This is the
LOW-end baseline; the 16+ Medium challenger (#32 cinder-bazaar) records its
cost against it.
