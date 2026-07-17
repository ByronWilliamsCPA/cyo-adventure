# Compliance report: the-vanishing-orchard (filled)

- **Cell**: 13-16 / long / prose (Wave 3)
- **Skeleton**: `skeletons/13-16/the-vanishing-orchard.json` (177 nodes, branch_and_bottleneck, tier 1, 33 endings)
- **Author model**: opus (Fable-outage routing)
- **Reviewer model**: opus (independent; verified graph dominance in python)
- **Disposition**: APPROVED (first-pass; one optional polish applied)

## Deterministic checks (final)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 138.9/node over 177 nodes (target 140, advisory 100-185, max 310)
findings=0 blocked=False safety_flagged=False
```

Zero RL-13 warnings (all 177 nodes in FK 5.5-8.5).

## Independent review: all 7 categories PASS, OVERALL APPROVE

This fill did not merely avoid the run's two failure modes but engineered
around them. Notable verifications by the reviewer (all via python dominator
checks):

- **Seed workaround CONFIRMED**: the keeper's seed is physically given only on
  the kee branch, but `n_b1` (the four-way confluence) re-grounds it and
  dominates 100% of the 16 downstream seed-using nodes; the origin-unstated
  framing contradicts nothing.
- Three route-specific skeleton beats were rewritten to universal facts
  (register names -> war-memorial names set at n_start; Odile's physical cord
  -> generic "rope of guardians"); substance preserved, no leak survives.
- Odile is cold-introduced with a full self-identifying appositive at the node
  that dominates all later references.
- All 33 endings match kind/valence with varied, grammatical rhythm; the
  punchy closers are complete sentences, not FK-tuning fragments.
- Sacrificial keeper imagery stays mythic (metaphysical fading, no bodily
  method, no imitable self-harm), and self-sacrifice-in-fear routes to setback
  endings while the celebrated resolutions reject anyone having to vanish.

## Polish applied (supervisor)

Optional item 1 (the only one applied): `kee_entry` now shows a glimpse of
Odile's knotted cord ("A long cord hung looped at her belt, knotted over and
over along its length, as if it counted something.") so the choice label
"Examine the keeper's knotted cord" is pre-visible. FK 6.94, in band.

Optional item 2 (deliberately NOT applied): the reviewer suggested framing how
the seed came into Rowan's hand for rec/cel readers, but the seed IS explicitly
given on the kee route, so any "she couldn't say how" framing would contradict
that branch. The current origin-unstated version is the correct choice; skipped.

## Supervisor adjudication

Approved. A controlled, genuinely literary fill: a folk-horror meditation on
grief and memory whose "hunger, not villain" theme lands through shared-keeping
rather than a death. 12 of 14 stories approved.

## Skeleton defect filed (pre-run production skeleton)

`skeletons/13-16/the-vanishing-orchard.json`: the keeper's-seed beats at
`n_b1`/`n_b2`/`n_b4` assume Rowan holds a token only the kee branch delivers,
and `kee_entry`'s choice label references a cord absent from its beat. The fill
compensates; a skeleton revision should ground the seed at the confluence and
seed the cord glimpse in `kee_entry`'s beat.
