# Parameterized-beat pilot: end-to-end results

Proof for the [story flexibility plan](../../docs/planning/story-flexibility-plan.md)
(WS-2). One parameterized skeleton, filled for two *new* themes, both passing the
safety gate.

## What was proven

`the-cave-of-echoes.parameterized.json` (8-11 short, time_cave, tier 1, 64 nodes,
16 endings) was filled twice from the same structure, binding its `{SLOT}`s to two
themes with no overlap with the original sea-caves story:

| Theme | Hero / companion / place | Integrity | Gate |
| --- | --- | --- | --- |
| Space station | Priya / repair-drone Pip / the derelict station Halcyon | ok (mean 92.7 words/node) | `blocked=False safety_flagged=False` |
| Dino dig | Theo / kestrel Comet / the Redwall fossil beds | ok (mean 75.6 words/node) | `blocked=False safety_flagged=False` |

Both fills: structure identical to the skeleton (only node bodies differ), zero
`<<FILL` markers, no leak of the original theme's proper nouns, no em-dash. All
gate findings were advisory RL-13 reading-level warnings (never blocking).

**Conclusion:** one structure generated two distinct, gate-passing stories. The
8-11 no-death guarantee held automatically for both, because the ending
`kind`/`valence` set is baked into the fixed structure and no slot can change it.
This is the core WS-2 claim, demonstrated.

## Refinement found: parameterize choice labels too

The neutralization pass rewrote node beats and ending titles but left
`choices[].label` strings untouched (choice labels are structure, so they were
out of scope for a beats-only transform). Both fill agents independently hit the
same tension: labels still carry sea-cave nouns ("Look closely at the orange
starfish", "Take the old brass compass", "beat the tide"). They bridged these in
prose (a fossilized sea star in the ancient seabed; a brass-cased handheld
navigator; runoff instead of tide), and it did not block the gate (labels are not
checked for theme coherence). But for a theme where those nouns make no sense,
this forces awkward in-fiction justification.

**Recommendation for WS-2:** extend parameterization to choice labels. A label is
an *action* the reader takes, so its slot must preserve the action semantics
(what choosing it does) while letting the theme supply the object, e.g.
"Look closely at {ROUTE_B1_PRIZE_OBJECT}" instead of the fixed "orange starfish".
This keeps labels theme-coherent without touching the branching structure the
labels encode.

## Reproduce

```
uv run python scripts/check_fill_integrity.py \
  out/pilot/the-cave-of-echoes.parameterized.json \
  out/pilot/fills/the-cave-of-echoes.space-station.filled.json
uv run python scripts/run_story_gate.py \
  out/pilot/fills/the-cave-of-echoes.space-station.filled.json
```
