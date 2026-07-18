# Compliance report: the-ashfall-expedition (Wave 4 gamebook fill)

- **Cell**: 16+ / long / gamebook (branch_and_bottleneck, 505 nodes, 143 endings) — the run's largest fill
- **Author model**: opus (Wave 4 capability test)
- **Reviewer model**: opus (independent; diffed all 505 nodes, sampled 14 beats nodes, traced 9 setbacks, ran a full pairwise similarity scan)
- **Disposition**: APPROVED for the fill stage (the one hard defect fixed by the supervisor; ending-cluster polish recorded as follow-up)

## Offline gate (reproduced, post-fix)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 76.8/node over 505 nodes (target 80, advisory 55-110, max 175)
findings=32 blocked=False safety_flagged=False   (all advisory RL-13)
```

## Review verdict (7 categories): all PASS (cat 7 with the one fixed defect), OVERALL SHIP

- **Structural integrity**: all 505 nodes diffed; zero non-body differences;
  zero FILL markers; zero empty bodies.
- **Beats fidelity**: 14 sampled nodes honor beats and set up exactly their
  choices.
- **Telegraphing**: 9 traced setbacks each legibly telegraphed; zero
  death/capture endings (140 setbacks + 3 positives), all retreat-framed.
- **Band policy**: 16+ ceilings not approached; no on-page violence, gore, or
  death; peril environmental (lava/tremor/ash/heat); grave, terse.
- **Word envelope**: mean 76.8, min 51, max 105, zero over the 175 hard max.
- **Ending grammar**: 18 sampled endings complete and varied; the 3 wins
  (triumphant / bittersweet / careful) distinct and well-crafted.
- **Prose/voice/surface diversity**: convincing terse second-person
  expedition-captain register; zero em-dash. The body-node diversity guard
  WORKED at 505 nodes: no body pair >85% similar, top opener reused only 49 of
  ~1500 sentences. The reuse recurred only in ENDINGS.

## The one hard defect (fixed by the supervisor)

The reviewer found two endings byte-identical: `n_e01_2` and `n_e05_1` (both
"Swallowed by the Marsh", same dune-country beat, reached from chapters b01 and
b05). Two byte-identical endings should never ship. Fixed: `n_e05_1` rewritten
with distinct structure and imagery (drowning cairns / ash-skin / a pole that
finds no bottom, vs the original's mule-and-stores slurry) while honoring the
identical beat; 67 -> 75 words, in-band. Verified: zero exact-duplicate body
groups remain; gate re-validated clean.

## Capability finding (the Wave 4 experiment)

**Opus gamebook-fill capability: STRONG** (fourth data point, at the largest
scale). At 505 nodes it held perfect structure, airtight telegraphing, faithful
beats, clean grammar, band-appropriate restraint, correct word envelope, and
(unlike drowned-court) genuine body-node surface diversity. The sole weakness
was mechanical under-diversification of parallel ENDINGS.

## Recorded follow-up (non-blocking, pre-public-launch)

Diversify the ~18 single-noun-swap ending clusters (largest: the 5-node "Driven
Down off the Ridge" and 4-node "Beaten Back by the Heat") beyond a terrain-noun
swap, and thin the four heavily-reused stock closer refrains across the 140
setback endings. Single-path exposure hides these; polish before public launch.
