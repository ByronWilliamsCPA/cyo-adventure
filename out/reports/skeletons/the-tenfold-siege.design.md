# Design report: the-tenfold-siege

- **Cell**: 16+ / long / gamebook (brief #36, Wave 5) — the 16+ Long dagger CEILING-CHALLENGER and the LARGEST skeleton of the run (low-end sibling: #35 the-pale-road, ~498 nodes)
- **Topology / tier**: gauntlet / 2
- **Designer model**: opus (gamebook batch; 5 repair cycles in the build + 1 supervisor-directed title repair)
- **Reviewer model**: opus (independent; full 9,832-config walk, best-win enumeration, title/body duplication clustering, ceiling assessment)
- **Disposition**: APPROVED for the fill stage (title-pool repair required by the review, applied and re-verified)

## Scripted validation (post-repair)

```text
stats: nodes=677 endings=209 fill_nodes=677 cell=(16+, long, gamebook) topology=gauntlet tier=2
ok: skeleton passes gate and brief checks
```

Reviewer confirmed (pre-repair, structure unchanged by the titles-only fix):
acyclic (zero cycles), longest path 84 edges (under the 93 cap), 21
reconvergence bottlenecks, 9,832 reachable configs uncapped, zero choiceless
states, exactly one conditional choice per reachable state at all 14 partition
nodes. Post-repair supervisor verification: 209/209 distinct titles, zero
duplicate node/choice ids, no truncated titles, no em-dash, longest path and
node count unchanged (confirming titles-only).

## State machine (three axes; the ten assaults are the ten checkpoints)

- `supplies` 0-3 (non-monotone: dec at command/heavy assaults, inc at quiet
  nights; gates the heavy-assault resolutions and the best win).
- `morale` 0-3 (non-monotone: inc/dec at command and survival; gates the
  finale reads).
- `breach` bool (set true only when assault 6 is held on an empty magazine;
  changes the later assaults and the finale).

## Review verdict (7 categories): all PASS, OVERALL SHIP (after the required fix)

- **Exact-partition + best-win exactness**: win_best reachable at exactly
  {breach:false, morale:3, supplies:2}, no leak; the 5 other wins occupy
  disjoint state regions; the 6th (win_nearthing) is the state-independent
  finale gamble.
- **Floor**: shortest satisfying completion exactly 37 (= the floor); depth 84
  <= 93.
- **Fair lethality**: all ten hazards specific; fatals legible; every
  Wait/Hold carries delay-is-death; deaths grave, terse, gore-free.

## Required fix applied (title-pool widen)

The review's one NO-SHIP-as-is finding: the 209 endings shared only 46 distinct
titles (eight titles each reused 7x). The reviewer argued convincingly this was
a mislabeled authoring economy, not a genuine ceiling property (the 453-node
cinder-bazaar achieved 141/141 distinct; the 530-node serpent-vaults 172/172),
and seven identically-named endings is a real UX defect on a production-eligible
skeleton. The designer re-composed the 203 fail titles as
`{failure-mode} at {place}` (and `{Answered Loud / Taken Alive} at {place},
{phase}` for the spotted deaths/captures), extracting the failure mode from each
fatal's own choice label, so the (assault x hazard x failure-mode) product is
unique. Result: 209/209 distinct, structure byte-identical, gate re-validated.

## Dagger-experiment finding (the headline: the extreme test)

The 677-node challenger produced the sharpest ceiling result of the run,
independently reproduced by the reviewer:

- **Correctness-by-hand genuinely breaks past ~600 nodes.** The load-bearing
  evidence is repair-cycle-5: the best win was originally gated on
  `supplies==3`, a state that is UNREACHABLE at the finale checkpoint (the
  command tradeoff spends the magazine to hold morale, so at fin_intact_hi the
  reachable supplies is {0,1,2}). This bug was invisible to inspection and only
  the Layer-2 config walk caught it. Cross-cutting state x 10 checkpoints x a
  finale cascade is exactly what a hand-author cannot verify reliably at this
  scale.
- **Content-distinctness does NOT break** structurally: the title recycling was
  an economy the author chose, not a ceiling forced it (proven by widening it to
  209/209 as a bounded mechanical fix).
- **CONCLUSION: ADR-011's ~460-node ceiling is confirmed as a HAND-REASONING
  SAFETY limit, not a structural one.** Past it, the config-walk gate becomes
  mandatory rather than optional: with the walk + a title generator, 677 nodes
  is maintainable; without the walk, hand-authoring at 677 ships latent
  dead-branch/misgate errors. The machine-checkable invariants (acyclicity,
  exact partition, reachability, word budgets) scale by construction at every
  size tested (306 -> 677).

## Design-note corrections (accuracy)

- supplies==3 AND morale==3 is not globally unreachable (542 early configs hold
  it); it is unreachable only at the finale checkpoint fin_intact_hi, which is
  what makes the supplies>=2 re-gate exact and single-config.
- Range-safety rests on saturating clamps (~452 clamp firings as routine gauge
  behavior), so the min/max declarations are load-bearing, not decorative.

## Notes for the future fill stage

Pin the finale cascade logic (breach -> intact/breached; then morale; then
supplies for the best win). The 167 death chains share a connective frame ("the
cold arithmetic of it"); the fill author must write from each ending's distinct
hazard and now-distinct title, not the shared frame.
