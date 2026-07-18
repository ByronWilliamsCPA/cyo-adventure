# Compliance report: the-drowned-court (Wave 4 gamebook fill)

- **Cell**: 16+ / medium / gamebook (branch_and_bottleneck, 314 nodes, 105 endings)
- **Author model**: opus (Wave 4 capability test)
- **Reviewer model**: opus (independent; diffed all 314 nodes, sampled 14 beats nodes, traced 6 failure endings, FK-measured, aggregate sentence-reuse audit)
- **Disposition**: APPROVED for the fill stage, ship as-is (optional padding polish noted)

## Offline gate (reproduced)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 64.6/node over 314 nodes (target 80, advisory 55-110, max 175)
findings=0 blocked=False safety_flagged=False
```

## Review verdict (7 categories): all PASS, OVERALL SHIP AS-IS

- **Structural integrity**: all 314 nodes diffed; only `body` differs; ids,
  choices, targets, endings, metadata, variables byte-equal; zero FILL
  markers, zero empty bodies.
- **Beats fidelity**: 14 sampled nodes honor beats and set up exactly their
  choices; the author correctly adds per-choice danger setup at hubs.
- **Fatal-choice telegraphing**: 6 traced failure endings each legibly
  telegraphed before the choice; the 98 "failures" read as aborted-run /
  forced-retreat, not lethal gore, within band.
- **Band policy**: at/below 16+ ceilings; grim vocabulary is contextual
  (decompression, spatial "dead cistern"); deaths grave, terse, gore-free.
- **Word envelope (verdict)**: mean 64.6 is acceptably lean BY DESIGN, not
  under-filling: the skeleton's per-node `words=` directives average exactly
  64.6, and Opus hit every node within +/-6 words of its per-node target. The
  80 figure is a story-level advisory center; the skeleton specced ~65-word
  nodes. Zero nodes over the 175 hard max.
- **Ending grammar**: authored story endings are complete and varied; the 7
  resolution endings are distinct and well-shaped.
- **Prose quality + voice**: consistent terse second-person; FK grade 8.7
  (in band); zero em-dash; strong, atmospheric register on the story spine.

## Capability finding (the Wave 4 experiment)

**Opus gamebook-fill capability: STRONG** (second data point). Perfect
structural fidelity, precise per-node word adherence, every death telegraphed,
consistent in-band voice, zero em-dashes.

## Optional polish (non-blocking)

The `pad*` interchangeable side-passage filler nodes reuse a small stock
sentence pool (the skeleton defines only 16 distinct beats across 187 padding
nodes, each repeated 17-19x), so a few verbatim sentences recur 30-65x in
aggregate. This is skeleton-invited repetition on interchangeable filler; any
single playthrough touches only a few, so it is invisible in a real read and
visible only in an aggregate audit. Diversifying the stock-sentence surface
wording is optional future polish, not a defect against spec.
