# Design report: the-tricameral-city

- **Cell**: 16+ / long / prose (brief #33, Wave 5)
- **Topology / tier**: sorting_hat / 1 (the run's largest sorting_hat at 240 nodes, 42 endings)
- **Designer model**: opus (Fable rate-limited; batch on Opus at the user's direction; zero repair cycles)
- **Reviewer model**: opus (independent; BFS/DFS traversal, per-track arity fingerprints, POV cross-track scans, telegraph path traces)
- **Disposition**: APPROVED for the fill stage (no fixes; one intentional thin-track flag for a future revision)

## Scripted validation

```text
stats: nodes=240 endings=42 fill_nodes=240 cell=(16+, long, prose) topology=sorting_hat tier=1
ok: skeleton passes gate and brief checks
```

Pure tree verified: three disjoint subtrees (Bench 64 / Prefecture 100 /
Register 73) + 3-node spine = 240, pairwise intersection empty, zero
cross-track edges, endings == leaves (42==42). Words/node 158-212. No
em-dash; no truncated titles. Every quantitative self-report (arity
fingerprints, floor, ending mix, subtree sizes) reproduced exactly.

## Structure summary

A young auditor's year inside one of three co-equal governing chambers of
Meridon: the Bench (judicial), the Prefecture (executive), the Register
(legislative/records). One civic scandal (the Deepstore grain shortfall and
the ~19-year "Abatement" cover) seen as three faces of one truth: a legal
fiction, a physical fiction (the vault substitution feeding uncounted outer
wards), and a numeric fiction (the founding Roll's over-count).

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Rhythm difference (weighted): genuinely distinct.** Arity fingerprints
  match exactly: Bench all-binary {2:12} late-clustered comb; Prefecture
  all-ternary {3:7} front-loaded; Register mixed {2:7,3:3} even cadence.
  Distinct on arity, count, and band-shape, not re-skins.
- **POV discipline (weighted): clean.** The vault substitution appears only
  in Prefecture (0 Bench, 0 Register); the sealed-consent binding only in
  Bench; the charter over-count and Ledd's memo only in Register. Broad
  cross-track hits were all false positives on generic words; the
  origin-over-count vs destination-undercount are correctly separated as
  complementary partial truths of one public gap.
- **Anchor consistency**: no chamber dissolved, no on-page death (the sole
  "drowns" is metaphor), Corvin Ash consistently the blamed bookkeeper,
  Tamsin Ledd reassigned not worse.
- **Floor (PL-20)**: shortest satisfying completion is depth 24 (three
  Prefecture wins tie); all sub-23 endings are non-satisfying setback/
  discovery.
- **Band fit**: institutional register throughout (complicity, forced
  resignation, renewed silence), no gore, no on-page death; no death or
  capture ending kinds.

## Intentional thin-track flag (not a fix)

The Prefecture's front-loaded all-ternary shape means only 2-3 decisions per
playthrough over 24-43 nodes (below the ~5-8 guideline). The reviewer
confirmed this and judged it shippable, not fixable-in-place: it is the
deliberate front-loaded pole of the three-track rhythm contrast, clears the
floor, and yields 15 distinct endings; adding decisions would degrade the
very arity fingerprint that makes the sort work. Recorded as the track to
enrich if a future revision wants more interactivity.

## Notes for the future fill stage

Pin the 219th Concord Year timeline (auditor sworn; the nine-hundred-measure
gap posted; Ledd's memo suppressed and she is reassigned; the Concordance
dates the Abatement at ~19 years; Ash forced to resign; the winter dole cut;
the Reckoning, which the Concord survives). Hold each chamber to its
POV-restricted mechanism; the public facts (the gap, the Abatement's
existence) are shared, the mechanisms behind them are not.
