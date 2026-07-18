# Design report: the-labyrinth-of-glass

- **Cell**: 13-16 / long / gamebook (brief #27, Wave 5) — the 13-16 Long dagger LOW-end skeleton (challenger sibling: #28 the-serpent-vaults)
- **Topology / tier**: gauntlet / 1
- **Designer model**: opus (gamebook batch; zero checker-fail cycles; one self-caught depth remediation)
- **Reviewer model**: opus (independent networkx traversal; re-derived every claim, extracted and de-duped all 94 dread beats)
- **Disposition**: APPROVED for the fill stage (no fixes; the slip-node divergence ruled acceptable)

## Scripted validation

```text
stats: nodes=383 endings=116 fill_nodes=383 cell=(13-16, long, gamebook) topology=gauntlet tier=1
ok: skeleton passes gate and brief checks
```

Reviewer confirmed: acyclic (zero cycles, zero back-edges), 18-checkpoint
spine with 18 reconvergence bottlenecks, win path 59 nodes (>= 32 floor),
longest path 62 nodes / 61 hops (under the 80 cap), 116 unique untruncated
titles, words 46-78 (13-16 gamebook envelope), no em-dash.

## Structure summary

A mirror labyrinth beneath an opera house: 18 checkpoints (Hall of False
Doors through the Hall of the Thousand Yous), each approach/gate/pass with a
co-located gamble. Wrong steps die in shallow off-spine chains; each gamble
either dies, is captured, or slips FORWARD onto the next checkpoint. 3 wins
off the final gate.

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Prose-variety guard (the pattern-setter's weakest rule): decisively
  fixed.** All 94 dread beats are DISTINCT (94/94, 100% unique), each
  referencing its own checkpoint hazard; every Wait/Hold fatal carries an
  explicit "delay is death" beat. This directly repairs the pattern-setter's
  4-directives-across-72-nodes defect and is the skeleton's strongest
  feature.
- **Gauntlet + acyclic**: verified; restart unrolled forward, no back-edge.
- **Fair lethality**: 6/6 sampled fatals are legible violations of stated
  gate rules; deaths grave, terse, gore-free.
- **Ratios**: 116/383 = 30.3% terminals (94 death + 19 capture + 3 wins); 38
  decisions.

## Slip-node divergence: acceptable adaptation (do not restore)

To keep the longest path under the depth cap, the designer folded the
pattern-setter's separate gamble "slip / barely made it" payoff node into the
gamble node itself. The reviewer ruled this acceptable, not must-restore, for
three reproduced reasons: (1) reconvergence is preserved (the gamble node is a
graph-distinct predecessor, so the next approach keeps in-degree 2); (2) the
near-miss beat survives inside the gamble node's body ("through by a hair and
stumbling into the next room with no breath to spare"); (3) the gamble stays
genuinely no-breather (two of its three choices are lethal). The only caveat
is presentational (a pure edge-destination view can't distinguish
survived-gamble from clean-pass), resolved one hop upstream at the gamble
node. Recorded as a sanctioned depth-headroom technique for later gauntlets.

## Baseline effort evidence (low-end dagger baseline)

One deterministic builder; zero checker-fail cycles (the gate passed on the
first invocation); the one structural revision was a self-caught depth
remediation (dropping the slip node cut the longest path from 80 at the cap to
62). Findings density low; the endorsed pattern transferred cleanly.

## Notes for the future fill stage

The uniform ap0/gate/pass template and 3-node death chains are the intended
gauntlet spine signature; the rooms and dread beats are fully individuated, so
the fill author has distinct per-checkpoint material. Keep deaths terse.
