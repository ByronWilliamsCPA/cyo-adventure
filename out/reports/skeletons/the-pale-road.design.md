# Design report: the-pale-road

- **Cell**: 16+ / long / gamebook (brief #35, Wave 5) — the 16+ Long dagger LOW-end skeleton (challenger sibling: #36 the-tenfold-siege)
- **Topology / tier**: gauntlet / 1
- **Designer model**: opus (gamebook batch; zero checker-fail cycles)
- **Reviewer model**: opus (independent; recomputed the longest path, de-duped all terminal and dread beats, audited the ending kinds against the prose)
- **Disposition**: APPROVED for the fill stage (one reviewer-recommended re-tag applied by the supervisor)

## Scripted validation (post-fix)

```text
stats: nodes=498 endings=150 fill_nodes=498 cell=(16+, long, gamebook) topology=gauntlet tier=1
ok: skeleton passes gate and brief checks
```

Reviewer confirmed: acyclic (zero cycles), 24-checkpoint spine with 24
reconvergence bottlenecks (each in-degree 2), win path 80 hops (>= 37 floor),
longest path 80 hops (under the 93 cap, margin 13, recomputed independently),
150 unique untruncated titles, words 62-92, no em-dash.

## Structure summary

A pilgrimage across a salt desert that unmakes the unprepared: a 24-checkpoint
single-spine gauntlet (Threshold Crust through the shrine rite), each
ap/gate/pass with a co-located gamble slipping forward. The canonical long
gauntlet at the envelope floor: one line, one law, walk it exactly or the
salt has you.

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Prose-variety guard: holds well.** 147/147 terminal beats distinct; 70 of
  121 dread beats distinct (max repeat 4x, far from the pattern-setter's
  4-across-72 collapse); 24 distinct hazards; 21 of 24 delay fatals carry the
  explicit delay-is-death beat.
- **Floor + depth**: floor and longest path coincide at 80 (pure spine, all
  bulk in shallow off-spine death chains); 80 >= 37 and < 93.
- **Terse word-mean: acceptable.** Mean 67.6 sits below the envelope center 80
  but above the approved pattern-setter (62.7) and inside the advisory band;
  driven by the 416 terse death-branch nodes, exactly where terseness belongs.
- **Ratios**: 150/498 = 30.1% terminals; 50 decisions; deaths grave, terse,
  gore-free.

## Fix applied (reviewer-recommended)

The 25 `_lost` "turned from the road" endings were tagged kind=setback but
their beats are prose-lethal (death-by-abandonment: "unmade by the salt, you
become one more the desert kept"). The reviewer's tonal verdict was that
all-lethal is the correct call for this premise, so rather than soften the
prose, the metadata was corrected: the 25 `_lost` endings are re-tagged
kind=death (valence unchanged). The ending mix is now an honest 147 death /
3 wins. Gate re-validated clean.

## Baseline effort evidence (16+ Long dagger low-end baseline)

One data-driven builder (a 24-entry hazard table); essentially one iteration;
zero checker-fail cycles (the gate passed first invocation), achieved by
front-loading a source read of the enforcement before writing. Confirmations
recorded for the challenger sibling: PL-20's win-floor counts only
success/completion (so the death re-tag does not change the floor); routing
the gamble survive-branch straight to the next approach (no interposed node)
keeps 24 checkpoints under the 93-hop wall.

## Notes for the future fill stage

Write the 25 turn-back endings as the abandonment-deaths they are (not soft
landings). Keep the one-law premise legible: every gate states the single
correct technique twice (in the ap and the gate) before the choice.
