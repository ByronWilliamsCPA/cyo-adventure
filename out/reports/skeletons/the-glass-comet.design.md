# Design report: the-glass-comet

- **Cell**: 10-13 / short / prose (brief #16, Wave 5)
- **Topology / tier**: branch_and_bottleneck / **2 (the run's first production stateful skeleton; tier-2 pattern-setter)**
- **Designer model**: fable (single design pass; a mid-run server error interrupted only the report, not the file)
- **Reviewer model**: opus (independent; re-ran the Layer-2 walk to verify)
- **Disposition**: APPROVED for the fill stage

## Scripted validation (final)

```text
stats: nodes=105 endings=20 fill_nodes=105 cell=(10-13, short, prose) topology=branch_and_bottleneck tier=2
ok: skeleton passes gate and brief checks
```

Layer 2 ran (tier-2 path in `run_gate`) and the reviewer independently drove
`walk_configurations` / `validate_layer2`: **638 reachable configurations,
capped=False, zero L2 findings, zero reachable non-ending state without an
enabled choice.**

## State machine (the reference design)

- **Variables (3)**: `plates` int 0-3 (init 3), `dome_oiled` bool (init false),
  `clock` int 0-4 (init 0: dusk -> first hours -> the clear gap -> late -> dawn).
- Theoretical var-space 4x2x5=40; 31 var-states and 638 (node, state)
  configurations actually reachable.
- 5 on_enter effect sites, 25 choice effect operations across 23 choices,
  14 conditional choices. All three variables verified load-bearing on
  OUTCOMES (reviewer confirmed each spans its full domain in reachable states).
- **Perfect-shot gate**: `n_done1` requires `dome_oiled==true AND clock<=2`;
  reachable only on attempt 1, so the best outcome is structurally earned and
  later retries cannot reach it.
- **Unrolled retry**: attempt1 -> reload -> attempt2 -> attempt3, each iteration
  consuming a plate and a clock band, self-terminating and acyclic (a literal
  cycle would trip PL-18's cyclic reclassification off branch_and_bottleneck).

## Review verdict (7 categories): all PASS, OVERALL APPROVE

Two non-blocking notes recorded (not fixed, deliberately, so the skeleton
ships and the notes become rules for later stateful briefs):

1. **Depth at cap (28/28)**: the longest path sits exactly at the (10-13,
   short) depth cap with zero margin. Validates green today; flagged as a
   fragility so future stateful skeletons leave 1-2 nodes of headroom.
2. **Decisions per real playthrough 8-11** (measured), above the ~4-7 brief;
   judged defensible for the oldest short band with light 2-way texture
   beats, but the ceiling to respect going forward.

## Tier-2 pattern rules (recorded for all remaining stateful briefs)

Carried to briefs #18, #20, #21, #23, #26, #28, #30, #32, #34, #36:

1. Keep state small (<= 3 variables); each variable gates a DIFFERENT outcome
   axis (capability / timing / inventory), verified by reachability spread.
2. Enforce an EXACT PARTITION at every convergence/resolution node: the
   condition set covers all reachable states with exactly one enabled choice
   (re-run `walk_configurations` to prove it; this is what keeps Layer 2 clean).
3. UNROLL retry/loops rather than cycling; each iteration consumes a monotonic
   resource so the chain self-terminates and stays acyclic.
4. Reserve the "perfect/best" outcome for a single early gated state so it is
   earned and later attempts structurally cannot reach it.
5. Every multi-parent node's FILL beat must be entry-agnostic AND carry
   explicit state-reflection instructions (reference plates/clock remaining).
6. Hold decision-clicks per real playthrough to ~8-10 max at 10-13; fewer for
   younger bands.
7. Leave 1-2 nodes of depth headroom under the cell cap; never ship at the cap.

## Notes for the future fill stage

The reachable-state context per node must be supplied to the author so prose
reflects the state that actually reaches each node (e.g. low plates read as
tension; dawn clock reads as the window closing). The 24 multi-parent beats
already carry entry-agnostic + state-reflection directives.
