# Compliance report: the-thornwood-trial (Wave 4 gamebook fill)

- **Cell**: 13-16 / long / gamebook (branch_and_bottleneck, 375 nodes, 115 endings)
- **Author model**: opus (Wave 4 capability test)
- **Reviewer model**: opus (independent; diffed all 375 nodes, sampled 12 beats nodes, traced 8 setbacks, ran an 85%-similarity pair scan)
- **Disposition**: APPROVED for the fill stage, ship-as-is for R1 (one non-blocking pre-public-launch diversity pass recorded)

## Offline gate (reproduced)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 67.7/node over 375 nodes (target 65, advisory 45-90, max 145)
findings=23 blocked=False safety_flagged=False   (all 23 advisory RL-13)
```

## Review verdict (7 categories): 6 PASS + 1 APPROVE-WITH-FIXES, OVERALL SHIP (R1)

- **Structural integrity**: all 375 nodes diffed; zero non-body differences;
  zero FILL markers; zero empty bodies.
- **Beats fidelity**: 12 sampled nodes each honor beats and set up exactly
  their choices.
- **Telegraphing**: 8 traced setbacks each legibly telegraphed before the
  choice; negatives are non-lethal setbacks (wait for searchers / turn for
  home / try again next season).
- **Band policy**: 111 setbacks + 4 positives; no over-ceiling terms (die/dead
  are metaphor); violence effectively nil; grave, terse, gore-free.
- **Word envelope**: mean ~68, min 53, max 103, zero over the 145 hard max. The
  disclosed per-node overage (endings ~62 vs 50 hint) is acceptable: the
  words= values are advisory hints, the aggregate is in-band, and endings stay
  terse; a defensible FK-7 tradeoff.
- **Ending grammar**: 17 sampled endings complete and varied; the 4 positives
  distinct and well-voiced.
- **Prose/voice/surface diversity (the one weakness)**: voice strong; zero
  em-dash; ZERO verbatim-identical bodies (literally true). But 288 pairs
  exceed 85% similarity (one reconnect pair at 99.4%, differing by a single
  word), because the author leaned on a small template pool with locale-token
  substitution on the skeleton-mandated parallel bottleneck/reconnect/ending
  nodes. Partly skeleton-forced (identical beats across parallel nodes) and
  invisible on any single playthrough, but the tightest clusters are a
  craftsmanship shortcut, not an inability (b_warren_4, b_grove_2 show genuine
  varied authoring). Non-blocking; not a gate/band/safety failure.

## Capability finding (the Wave 4 experiment)

**Opus gamebook-fill capability: STRONG.** Flawless structural/beats/
telegraph/band/word/grammar execution; the only blemish is over-reliance on
locale-token templating for skeleton-mandated parallel nodes.

## Recorded follow-up (non-blocking, pre-public-launch)

Queue a diversity pass on the ~8 near-verbatim template clusters the reviewer
named (the "wrong footing," "the gap shrinks," "you do nearly everything
right," and the `rc_*_0_2` reconnect lines): re-author with structural
variation beyond a single noun swap. Shippable as-is for R1 given single-path
exposure; this is a polish item, consistent with the run's other
skeleton-invited-reuse dispositions.
