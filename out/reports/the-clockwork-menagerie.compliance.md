# Compliance report: the-clockwork-menagerie (filled)

- **Cell**: 8-11 / long / prose (Wave 3)
- **Skeleton**: `skeletons/8-11/the-clockwork-menagerie.json` (166 nodes, branch_and_bottleneck, tier 1, 27 endings)
- **Author model**: opus (fill + 1 repair cycle; Fable-outage routing)
- **Reviewer model**: opus (independent; ran dominator checks on the graph)
- **Disposition**: APPROVED (supervisor-verified after repair cycle 1)

## Deterministic checks (final)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 102.8/node over 166 nodes (target 100, advisory 70-135, max 220)
findings=0 blocked=False safety_flagged=False
```

Zero RL-13 warnings (all 166 nodes in FK 3.0-6.0). First Wave 3 story.

## Independent review (initial verdict)

Categories 1, 2, 3, 4, 6, 7 PASS. Category 5 (continuity) FAIL.

Notable: the reviewer independently ran the dominator-check technique on the
graph and CONFIRMED the 12 true bottlenecks are provably route-neutral (n_key
dominates all master-key uses; n_spring -> n_shop -> n_hub chain dominates the
spare-mainspring and Fettle's-instructions assertions). The ending-grammar
pass held (no fragments at any of the 27 endings). The failures were a class
of cross-wing recall leaks in the single-parent "mend one creature" finale:
nodes reachable without visiting a wing yet asserting an item (the tiny
winder, acquired only in the conservatory A-branch) or a memory (the
elephant's prior fright, only on a savanna route).

## Repair cycle 1 (opus author; supervisor-verified)

The four flagged nodes fixed, plus three same-class sibling leaks the author
proactively caught (fh_fx_lion "crossed back"/"now", fh_fx_whale "back",
fh_fx_eleph2 "frightened her"). Finale items are now sourced on-site in the
scene (aviary winder from a keeper stand; conservatory winder from its stand,
present tense) or framed as known museum exhibits (the elephant's lurching as
general reputation, not Nia's memory). Supervisor scan confirms no residual
prior-visit / prior-fright / pocket-item phrases (the one "again" hit is
within-scene mechanism motion, not a prior visit). All edited nodes FK 4.1-5.9.

## Supervisor adjudication

Approved. A genuinely accomplished long fill: atmospheric, on-band, with
disciplined "both ways / all three ways" convergence writing on the true
bottlenecks and a clean finale after repair. 11 of 14 stories approved.

## Skeleton defect filed (pre-run production skeleton)

`skeletons/8-11/the-clockwork-menagerie.json`: the finale beats at
`fh_fx_bird`, `fh_fx_fly`, `fh_fx_eleph`, `fh_fx1` (and siblings) themselves
assume cross-wing recall ("the little winder", "the seed-small winder", "that
frightened her earlier"). The fill compensates in prose, but the beats should
be reworded to source items on-site and frame exhibits by reputation, so a
future fill is not pushed toward the same leak.
