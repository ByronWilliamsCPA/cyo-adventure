# WP-0.4 continuity read: The Sky-Ship Stowaway (revised edition)

Second-reader continuity pass over `out/the-sky-ship-stowaway.filled.json` (WP-0.4). Pre-fix book sha256
`bb215b407e972124f4f646c194916059bd96b0c76f00fb51006ea21d2b765d24` (commit `60f1001`): 123 nodes, 151 choices,
23 endings, bool variables `fed_pip`, `knows_ropes`, `told_bosun`, `fin_free`. The reader did not write the book
or the plan. (Written to the repo by the orchestrator from the reader's report, because the harness refused the
reader's own write of this file.)

**Method.** Every route played with `StoryEngine` depth first from `n_open`: 41,460 complete routes, 487 reachable
(node, state) configurations, 123/123 nodes, no dead ends. Each route carried the plan's known-on-entry set, and each
node's `requires` was checked on every route. Every body and label was then read against its inbound routes and states,
and every merge and edited node was replayed in flow. The plan's `requires` lists are sparse, so most findings came
from reading. No "Wren" in book or plan.

Severity: blocker (plain contradiction), should-fix (unshown presupposition), minor (small wording presupposition).

## Blockers

**F3. Pip "in her coat" where he was last on the floor.** `unestablished_fact_on_route`. Nodes `b_steer1` ("inside
her coat, Pip shifted and stretched"), `b_steer_purr` ("Bree lifted Pip out of her coat"), `b_tell_doubt` ("a
stranger with a cat in her coat"). Route `... c_storm_deck > c_deck_a > c_deck_a_go > c_deck_mid_go >
c_secret_people > c_people_cold > c_people_cold_go > c_people_mid_go > c_bridge_steer` (`fed_pip=true`):
`p_people_cold` had "with Pip trotting behind like a very small escort". Also `... c_storm_hold > c_hold_hatch >
c_shold_a_go > c_hold_mid_go > c_secret_reveal > c_reveal_a > ... > c_bridge_steer`: Pip "went in first" at
`s_hold_mid` and was never put back. `p_save_mid` only "scooped up Pip". Fix: each route out of the hold puts him in
the coat (`p_save_mid` "scooped Pip into her coat"; `p_reveal1` "tucked Pip into her coat ... Pip peered out at the
water"; `p_reveal_a` "rode in her coat with his chin on her collar"; `p_people1` "tucked Pip into her coat and ran to
fetch help"; `p_people_cold` "Pip peered out of Bree's coat like a very small lookout"). Plan: facts
`pip_in_coat_bridge` and `pip_in_coat_storm`.

**F8. "Nobody told me, I just looked" after being told to look.** `state_contradiction`. Node `p_people_b`. Route
`... c_storm_crew > c_crew_a > c_crew_a_go > c_crew_mid_go > c_crew_truth_go > c_secret_people > c_people_b`
(`told_bosun=true`; the bosun said "go and see, and come and tell me"), and the `s_deck_a` route (the officer said
"find out what in thunder is groaning down there"). Fix: "how did a girl with a cat in her coat get past my sealed
door?" / "The storm shook it open, and I went in." Plan: fact `storm_opened_hold_door`.

## Should-fix

**F1. "So this was Nimbus, the captain's secret."** `n_secret` (also `p_people1`). Route `c_open > c_start_eng >
c_eng_deep > c_eng_b > c_eng_b_go > c_eng_b2_go > c_eng_conv_go > c_friend_rig > c_rig_a > c_rig_a_go > c_rig_mid_go
> c_storm_crew > c_crew_a > c_crew_a_go > c_crew_dodge > c_crew_dodge_go`, all false. The dodge route showed only "a
great door marked SEALED", so the reader has no link between the hold and the captain, and the plan's
`captain_secret_cargo` is unmet. Fix: `s_crew_dodge` "A board nailed across it said SEALED BY ORDER OF THE CAPTAIN,
but the storm had shaken the bolt loose." Plan: `s_crew_dodge` establishes `captain_secret_cargo`.

**F2. "The other was still strapped flat by the twisted harness."** `e_neu_kite`. Route `... c_deck_mid_go >
c_secret_pip > c_pip_go > c_save_mid_go > c_bridge_free > c_free_tangled` (`fed_pip=true`); any route that skips
`p_save1`. The strap was never shown. Fix: "pinned flat against his side by a twisted strap of his harness". Plan:
establishes `fin_strapped` instead of requiring it.

## Minor

- **F4.** `n_bridge` "You have been nearer to him tonight than any of us": on the `p_people_a` and `p_people_cold`
  routes nothing on the page tells the captain. Fix: the bosun bellows for her to come and hear what the small fry
  found ("hear this one").
- **F5.** `p_people1` "The captain was the only one who knew" contradicts the officers overheard at `f_cabin_a` and
  `f_cabin_b2`. Fix: "The captain knew what was truly in that hold."
- **F6.** `b_steer_purr` "the spot under his chin that she had discovered in the larder": `f_galley_a` never shows it.
  Fix: "She scratched him under the chin".
- **F7.** `f_cabin1` "The voices came" with no voices introduced (route `... c_friend_cabin`). Fix: "Voices came".

## Checked, not defects

Pip at `n_storm` (all `f_*_mid` tuck him in), `n_secret`, `n_bridge`, `p_people_mid`. All twelve setback and neutral
endings reread in flow. Low-hum, free, inner-bay and captain chains. No payoff leans on another payoff. `truth` never
contradicted. Ship timeline (mid-voyage mooring stop, Pip aboard six weeks).

## After the fix

41,460 routes, 487 configurations, zero `requires` misses against the updated plan. Edited nodes replayed in flow.
**Open findings: 0.** Bodies changed in 10 nodes; nothing added or retargeted. Gate exit 0 (`findings=0`),
`run_fill_gate` not blocked, prose-craft `--check` exit 0. `check_fill_integrity.py`: markers, words and fill-rate ok;
`structure` fails as expected for a revised book (it failed before this pass too). Against a skeleton built from the
pre-fix book, every line passes, which shows the pass changed prose only. `scripts/check_story_plan.py` reports zero
errors on the fixed book and plan.
