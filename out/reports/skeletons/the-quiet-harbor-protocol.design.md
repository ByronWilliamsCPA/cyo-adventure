# Design report: the-quiet-harbor-protocol

- **Cell**: 16+ / medium / prose (brief #30, Wave 5)
- **Topology / tier**: branch_and_bottleneck / 2
- **Designer model**: opus (Fable rate-limited; batch moved to Opus at the user's direction; zero repair cycles)
- **Reviewer model**: opus (independent; reproduced the full 946-config walk through the real Pydantic model, the four exact-partition gates, the best-outcome enumeration, and the n_pier dominator chain)
- **Disposition**: APPROVED for the fill stage (no fixes required)

## Scripted validation

```text
stats: nodes=153 endings=28 fill_nodes=153 cell=(16+, medium, prose) topology=branch_and_bottleneck tier=2
ok: skeleton passes gate and brief checks
```

Layer-2 walk: 946 reachable configurations, capped=False (complete state
space), all 28 endings reachable. Words/node 148-190. No em-dash; no
truncated ending titles (supervisor scan).

## State machine (three axes, each read at a distinct gate)

- `evidence` 0-3 (monotone corroborated proof; +1 at most once per
  investigation leg).
- `exposure` 0-2 (visibility; clamps at 2; increments on bold entries).
- `flagged` bool (tipped the adversary / carry a compromised artifact; set
  only by the three line-crossing choices).

Reviewer confirmed ranges hold exactly, flagged is set only by the three
cross choices (no on_enter setters), and each axis is read at a different
gate (n_approach by exposure, n_read by flagged, n_clean/n_burned by
evidence).

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Exact-partition (the tier-2 b&b contract): clean.** Reproduced via the
  same walk_configurations the gate uses: zero reachable choiceless states,
  and every reachable state at all four gates has exactly one enabled
  choice. Partitions are exhaustive and disjoint.
- **Best-outcome exactness: verified.** The clean-rollup completion
  c_e3_scene is reachable only at {evidence==3, flagged==False} (exposure
  free); no flagged==True config reaches it.
- **Leak/dominator: clean.** n_pier (in-degree 3) and the three leg mids
  (in-degree 10) carry arrival-agnostic directives; the n_pier dominator
  chain confirms no Corbett-fist or Ashe-brief detail leaks into any shared
  node.
- **Anchor consistency: clean.** Petrel genuine/loyal, Corbett the mole,
  Ashe loyal-but-suspect in every branch; the burned-branch "bait or
  doomed" phrasing is Nell's blind uncertainty, not a world-claim.
- **Band fit**: 4 death + 4 capture endings, all telegraphed (reachable
  only after a stated tradecraft break); the drown-Corbett ending is gated
  behind an explicit line-crossing choice and framed as "a clean win with a
  stain she chose." Dread/tradecraft register, no gore.

## Notes for the future fill stage

Pin the fact sheet (HARBOR protocol history, the Meridian collapse, the
countersign "the tide runs both ways / and the gulls remember", the
immutable traitor=Corbett / asset=Petrel / Ashe-loyal facts, the two-night
timeline). Hold n_pier and the three leg-mid nodes strictly arrival-neutral.
Keep the four deterministic gate nodes (single visible choice) reading as
inevitability, not dead clicks.
