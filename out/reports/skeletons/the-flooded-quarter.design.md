# Design report: the-flooded-quarter

- **Cell**: 10-13 / medium / prose (brief #18, Wave 5)
- **Topology / tier**: open_map / **2 (first stateful open_map; pattern-setter for the tier-2 + open_map combination)**
- **Designer model**: fable (design survived two outage interruptions; zero repair cycles)
- **Reviewer model**: opus (independent; reproduced the full Layer-2 walk and config-space claims; review itself resumed across a session-limit interruption)
- **Disposition**: APPROVED for the fill stage (one optional guidance polish applied by the supervisor)

## Scripted validation (final)

```text
stats: nodes=155 endings=28 fill_nodes=155 cell=(10-13, medium, prose) topology=open_map tier=2
ok: skeleton passes gate and brief checks
```

Layer-2 walk: **19,236 reachable configurations, capped=False, zero L2
findings**; reviewer independently confirmed the best-outcome gate is exact
(`fin_full` appears in the config space ONLY at water==2).

## State machine (the stateful open_map reference)

- `water` 0-2 (timing: once-per-spoke increments, so water = min(errands, 2);
  the flood level IS the clock and the city mutates under the reader).
- `oil` 0-3 (capability: five oil-gated dark-work choices, hub refill).
- `laden` bool (inventory: load/board choices; auto-unload on_enter at the
  hub and the finale muster).
- Reviewer-verified: every one of the 15 gated nodes retains at least one
  unconditional companion choice; the hub/muster safety valves hold across
  all configs; graded finale (zero errands = the humbler dawn; two errands =
  the crest and the fullest endings, e_lantern/e_keeper).

## Review verdict (7 categories): all PASS, OVERALL APPROVE

Highlights: the additive-over-unconditional-base relaxation of the
exact-partition rule was ENDORSED as the open_map precedent, with its
soundness invariant made explicit (valid only while every gated node keeps a
verified unconditional companion). Kid-never-in-water verified beat by beat
(the only "swimming" token is a dog at dawn); "defer to the brigade" framed
as dignified courage; Brice's dispatch rules durable across all spokes and
the finale.

## Polish applied (supervisor, reviewer-suggested)

`os_done` and `ph_cross` beats now carry author guidance that a cross-spoke
hop can arrive with a prior errand's load aboard, so the cargo state is
written deliberately rather than by omission. Gate re-validated clean.

## Tier-2 open_map pattern guidance (recorded for briefs #21/#26/#30/#34 and gamebooks #23/#28/#32/#36)

1. Base-plus-adds is the sanctioned open_map relaxation of exact-partition,
   valid ONLY when every gated node keeps a verified unconditional companion
   (assert uncond >= 1 per gated node at author time).
2. Put the best outcome behind a single monotone progress variable that
   increments once-per-spoke and caps below the spoke count; verify in the
   config space that the best-outcome node appears at only the gate value.
3. Auto-reset inventory state on_enter at BOTH the hub and the finale
   muster; if cross-spoke hops exist, confirm gates make laden entry safe
   and add author guidance for the unremarked-cargo state.
4. Every reconvergence and cross-entry node carries an explicit
   "write arrival-neutral" directive; recaps cite only path-universal causes
   (an offstage upstream cause is the clean way to write a shared finale).
