# Design report: the-year-of-four-banners

- **Cell**: 13-16 / long / prose (brief #25, Wave 5)
- **Topology / tier**: sorting_hat / 1
- **Designer model**: opus (Fable rate-limited; batch moved to Opus at the user's direction; zero repair cycles)
- **Reviewer model**: opus (independent; rebuilt the parent map and BFS subtrees, enumerated all 33 root-to-leaf paths, traced POV and telegraph claims)
- **Disposition**: APPROVED for the fill stage (no fixes; two defensive advisories for the fill/edit stage)

## Scripted validation

```text
stats: nodes=212 endings=33 fill_nodes=212 cell=(13-16, long, prose) topology=sorting_hat tier=1
ok: skeleton passes gate and brief checks
```

Pure tree verified: three disjoint subtrees (Grey 83 / Red 56 / Green 70) +
3-node spine = 212, pairwise overlap 0, zero cross-track edges, endings ==
leaves (33==33). Words/node 128-178. No em-dash; no truncated titles.

## Structure summary

A royal succession year in Veldmark witnessed from one of three contending
houses (Grey/Vane, Red/Corven, Green/Miren). The "four banners" tension is
resolved with the gold heron of the dead king's line: the nine-year-old
heir Doran, playable by none, orbited by all three houses. Your banner
decides which betrayals you witness.

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Rhythm difference (weighted): confirmed distinct.** Red is an
  unmistakable late comb (13-node single-choice spine then 12 consecutive
  binaries). Grey front-loads with two ternary fans and stops deciding at
  depth 14. Green is a steady all-binary metronome sustaining a cadence out
  to depth 16. The grey-vs-green margin is real but thin; distinctness
  rests on arity signature (Grey has ternaries, Green is 100% binary),
  count (7 vs 9), and band shape, not central tendency.
- **POV discipline (weighted): clean, written defensively.** The Bridge
  drowning is not knowable from Red (r_s6 explicitly withholds it); the
  staged poisoning is never witnessed by Green (zero feast nodes in the
  subtree); the sellsword-letter proof exists only in Green's hands. The
  leak-prone boundaries are guarded in the beats themselves ("a proven
  truth and a known truth are not the same weapon").
- **Anchor consistency**: Doran survives every track (never killed
  on-page); the bridge/feast/letter attributions are consistent across all
  three houses.
- **Floor (PL-20)**: shortest satisfying completion is exactly 20 (six
  leaves tie); all sub-20 endings are non-satisfying (setback@14,
  capture@15, death@17).
- **Band fit**: the single death ending (Vane's fall) is offstage with
  gravity, no on-page death or gore; the two captures are political
  (cage/hostage, child-as-shield), morally heavy but band-appropriate.

## Defensive advisories (for the fill/edit stage; no change now)

1. **Protect the grey-vs-green rhythm margin**: do not remove Grey's two
   ternary choices (g_will, g_z_offer) or shorten Green's deeper cadence
   (its decisions out to depth 16). Either edit would collapse the thinnest
   distinctness margin in the design.
2. **Do not strengthen Grey's feast half-proof**: Grey holds suspicion plus
   a half-proof of the staged poisoning, deliberately short of the
   Red-only provable staging. A careless rewrite that lets Grey definitively
   prove the Duke staged it would tip into a POV leak.

## Notes for the future fill stage

Pin the succession-year anchor timeline (Midwinter king dies; will names
Vane regent under three-house co-sign; Corven's secret sellsword letter;
the Kingsbridge drowning of forty river folk by Vane's order via Sarn; the
staged Heron Feast; Corven takes Doran to Redwater; the Chancery leak; the
Redwater siege). Hold each betrayal to its POV-restricted vantage.
