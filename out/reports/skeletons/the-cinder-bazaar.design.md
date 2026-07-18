# Design report: the-cinder-bazaar

- **Cell**: 16+ / medium / gamebook (brief #32, Wave 5) — the 16+ Medium dagger CEILING-CHALLENGER (low-end sibling: #31 the-red-meridian-run, ~306 nodes)
- **Topology / tier**: branch_and_bottleneck / 2
- **Designer model**: opus (Fable rate-limited; gamebook batch on Opus; 3 repair cycles, all bookkeeping)
- **Reviewer model**: opus (independent; reproduced the full 3,440-config walk, the exact-partition gates, the best-outcome enumeration, the dominator tests, and independently clustered the ending-beat duplication)
- **Disposition**: APPROVED for the fill stage (no fixes; templated endings resolved as acceptable-with-note)

## Scripted validation

```text
stats: nodes=453 endings=141 fill_nodes=453 cell=(16+, medium, gamebook) topology=branch_and_bottleneck tier=2
ok: skeleton passes gate and brief checks
```

Reviewer reproduced: acyclic (zero cycles), longest path 39 edges (under the
73 cap), 3,440 reachable configs uncapped, zero choiceless states, exactly
one enabled choice per reachable state at all seven gates, 141 endings all
distinct titles, no em-dash. Aim-high node target hit (453 in the 440-475
challenger band).

## State machine (three axes)

- `water` 0-3 (survival; consumed on hot crossings, +1 at the clean seep;
  read at the Cistern and the finale).
- `goods` 0-3 (inventory/route; +1 on advancing exits; read at the
  Caravanserai and the finale).
- `marked` bool (hunted/safe-exit; set by blood/brawl approaches; read at the
  Cinder Gate and the finale).

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Exact-partition**: zero choiceless states; one enabled choice per state
  at every gate across all 3,440 configs.
- **Best-outcome exactness**: e_best reachable at exactly 3 configs, all
  {marked==false, goods==3, water>=1}; no leak. The other two wins are
  success-kind and deep.
- **Dominator/leak**: a1_gate and a2_gate (in-degree 21) dominate e_best and
  are arrival-neutral; the multi-parent act-entry nodes carry pure locale
  setup, no route leak.
- **Floor/ratios**: playable floor 34 (>= 29); 141/453 = 31.1% terminals; 60
  decisions; all 117 death/capture titles distinct and locale-specific; every
  sampled fatal telegraphed; deaths grave, gore-free.

## Dagger-experiment finding (the point of this challenger)

The reviewer independently reproduced BOTH halves of the designer's thesis
and delivered a clear ceiling verdict:

- **Machine-checkable invariants scale by construction.** Acyclicity, exact
  partition, reachability (3,440 uncapped), best-outcome exactness, floor,
  ratios, and word budgets ALL held at 453 nodes and did NOT degrade with
  scale. Structural machinery was never the binding constraint. All 3 repair
  cycles were bookkeeping (duplicate ending titles, 12 duplicate choice ids,
  a node-count undershoot), not logic or topology.
- **Distinct-content is the real limit.** The reviewer clustered the endings:
  80 of 141 (57%) collapse into three near-duplicate clusters of a single
  death-beat template, varying only the hazard noun across ~40 distinct
  hazards. This is confined to the intentionally-uniform tone directive;
  distinct per-ending hazard, telegraph, and hand-authored title carry the
  meaningful variation into the fill stage, so it is a fill-stage quality
  RISK, not a skeleton defect.
- **CEILING VERDICT: ADR-011's ~460-node hand-authoring ceiling is ABOUT
  RIGHT.** A 453-node graph is maintainable, but maintainable is not the same
  as distinctly hand-authored; the ceiling shows itself as diminishing
  distinctiveness per node (having to template the death beat over 80+
  endings to fill the terminal count), not as a broken invariant. This
  skeleton is evidence FOR the ceiling. Pushing materially past it forces more
  template reuse or assisted generation for the death-beat layer. (The
  600-680-node #36 tenfold-siege will test the extreme.)

## Cosmetic self-report corrections (no node edits)

Designer said a3_enter in-degree 2 (actual 3) and floor 33 (actual 34);
neither affects the skeleton.

## Notes for the future fill stage

The 80 templated-beat death endings are the real risk: the fill writer must
write from each ending's DISTINCT hazard/telegraph/title, not the shared tone
directive, or the grim fails will read samey. Hold the gate nodes and act
entries arrival-neutral (they already self-police).
