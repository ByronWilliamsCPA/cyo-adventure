# Compliance report: the-hollow-lighthouse (filled)

- **Cell**: 10-13 / medium / prose (Wave 2)
- **Skeleton**: `skeletons/10-13/the-hollow-lighthouse.json` (148 nodes, branch_and_bottleneck, tier 1)
- **Author model**: sonnet (initial fill + 2 repair rounds; fill interrupted once by a usage limit and resumed cleanly)
- **Reviewer model**: sonnet (independent, fresh context)
- **Disposition**: APPROVED (supervisor-verified after repairs)

## Deterministic checks (final)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 90.7/node over 148 nodes (target 100, advisory 70-135, max 220)
findings=0 blocked=False safety_flagged=False
```

Zero RL-13 warnings (first draft had 91/148; converged via the validator's
own FK oracle).

## Independent review (initial verdict)

Categories 2 (content policy), 3 (beats fidelity), 7 (safety) PASS.
Categories 1, 4, 5, 6 FAIL:

- Continuity (critical): three route-specific-item breaks at the tunnel
  bottlenecks: a brass key possessed on only 3 of many routes, a lantern
  granted on one sub-path, and a torn-page cross-reference from one route.
  ROOT CAUSE: all three assumptions originate in the SKELETON's own beat
  text; the fill reproduced them.
- One ungrounded choice (`n_chamber` "head back to town").
- Mechanical template flattening: "She could [A]. Or she could [B]." in
  30 of ~59 choice nodes; a five-sentence "She..." run in one ending; a
  templated "settle in and wait" setback closer; one duplicated phrase.

## Repairs (supervisor-verified)

1. Key made ambient (left forgotten in the lock; no possession claim).
2. Lantern grounded UNIVERSALLY: the skeleton's choice labels hardcode a
   lantern, so it could not be removed; a storm lantern + matches beat was
   added at `n_tunnel`, the 6-parent bottleneck every route crosses, and
   downstream references tied to it. Contradiction scan over all tn_*/cm_*
   nodes clean.
3. Ledger box made self-contained (no torn-page cross-reference).
4. `n_chamber` leave-choice grounded (hour, cold, fatigue).
5. Ending rhythm fixes + template variation across 14 choice nodes
   (question forms, observation-implies-options, mid-action deliberation);
   all edited nodes FK-verified 4.0-7.0.

## Skeleton defect filed (pre-run skeleton, not Wave 5)

`skeletons/10-13/the-hollow-lighthouse.json` beats at `tn_keeper`,
`tn_store_join`, and `tn_store_box` assume route-specific items ("the brass
key she carried", "her borrowed lantern", "the torn page") that only some
routes grant. The fill now compensates in prose, but a future skeleton
revision should reword those beats to be route-neutral. Recorded here as
the authoritative note; also relevant as a checklist item for Wave 5
reviews (which already test for exactly this class).

## Supervisor adjudication

Approved. Reviewer's craft note: the clue-relay mystery plays fair and the
bottlenecks are well-disguised; the FK remediation genuinely worked. New
process rule confirmed: fill-time repair rounds must re-validate CROSS-PATH
logic, not just the edited node.
