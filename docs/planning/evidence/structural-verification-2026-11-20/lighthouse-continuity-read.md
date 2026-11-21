# Continuity read: The Hollow Lighthouse (revised edition)

Independent, read-only continuity read of `out/the-hollow-lighthouse.filled.json` as integrated on
2026-11-20 (commit `15b14a1`, "feat(stories): give The Hollow Lighthouse consequences, voices, and endings that
pay off"). Recorded here because the findings were reported in-session and never written to the repo, and
`story-plan-implementation-plan.md` (gate G1, WP-1.3, WP-0.4) uses them as known answers.

**Method.** All 162 node bodies, every choice label, condition and effect, and each node's inbound routes and
reachable variable states were read; a breadth-first search over (node, state) found 1,214 reachable pairs. A
script-chosen set of 46 playthroughs covers 162 of 162 nodes and 32 of 32 endings, but the read itself was done in
graph order, checking each node against its inbound routes and states, not as 46 separate runs. No dead ends: every
non-ending node has a visible choice in every reachable state. The backbone (the light is the smuggler's landing
lamp; the keeper set it blinking "keep off") is never contradicted.

**Status.** None of these defects has been fixed. A fix pass was started and stopped by the owner's 2026-11-20
pause on book editing (register row `UW-M20`); the book file on the branch is unchanged since `15b14a1`.

## Blockers (a careful reader will notice a plain contradiction)

| Id | Node | Sentence | Route and state | Why it is wrong |
| --- | --- | --- | --- | --- |
| B1 | `e_win_keeper_word` | "'Minded the bog, I see,' he said." | `n_chamber > c_n_chamber_1 > cm_letter > c_cm_letter_1 > cm_letter_read > c_cm_letter_read_1 > cm_letter_map > c_cm_letter_map_2`; any state | The ending is shared. On this route Mira never met Ferris; his "mind the bog by the second gate" is said only in `cm_cottage_wait`. |
| B2 | `e_set_gears` and `cm_light_relight` | "It had wanted a key with a square end, and somewhere in this lighthouse there was one." / "'Where is your key, then?' Mira asked the lamp." | `cm_light > c_cm_light_1 > cm_light_relight > c_cm_light_relight_2 > e_set_gears`; `has_key = true` | Choice 2 is visible in both states. A reader holding the tagged "Wind her slow" key is told she has none and must find one. |
| B3 | `e_win_harbor` | "Mira did not know the name. 'He has a grey boat,' she said." | `jr_smug > c_jr_smug_2 > jr_smug_names > ... > n_chamber > cm_smug > c_cm_smug_1 > cm_smug_photo > c_cm_smug_photo_2`; any state | A reader who passed `jr_smug_names` learned the name Varley. A reader who saw neither `b_gallery_edge` nor `e_set_gate` has never seen a grey boat. Same unseen-boat leak in narration at `cm_smug_follow` and `e_neutral_honest` (should-fix). |

## Should-fix

| Id | Node | Defect |
| --- | --- | --- |
| S1 | `e_win_promise` | On the letter-and-plea route Mira does not know where Ferris lives, yet "he fetched the old man down from the moor by noon"; she also "went down to the journal on its stool" although `cm_leave` has her carrying it. |
| S2 | `b_clock_chain`, `a_shelf_books`, `c_arch_marks`, `jr_light_read`, `jr_tun_stone`, `d_loft_up`, `e_set_d_loft` | The lamp code and "keep off" reveal is delivered as a fresh realisation several times on one path; `jr_light` and `jr_light_read` are reachable with `knows_code` already true. |
| S3 | `n_chamber` | "a store that smelled of tar behind her, two lamps over her head" is not true on the `tn_cut` and `tn_gate` routes, which never enter the store, nor for readers who never saw the great lamp. |
| S4 | `e_set_a_drawer` | "two forks from the kitchen" on a path that never visits the kitchen; this ending and `e_set_cellar` give back little. |

## Minor

- M1: `c_c_arch_gap_1` "Back out and try the other opening" lands on `c_gather`, whose opening does not show it.
- M2: `c_tn_gate_open_1` and `c_tn_cut_2` both land on `n_chamber`, which opens "Beyond the door"; `tn_gate_open`
  never shows the swells or the steps.
- M3: `e_set_stair` says the eighteenth step; the hollow step in `st_wind` is the nineteenth.
- M4: `cm_light_true` "as the tag said": the key from `c_pool_metal` has no tag; "forty turns" also clashes with
  `e_win_promise`.
- M5: `tn_store_box` has Mira take the ledger, which is never mentioned again.
- M6: `tn_gate` has two consecutive sentences starting "Mira".
- M7: `e_win_signal` ends on an unresolved mystery under a "Signal Solved" positive title.
- M8: "A year of dust" in rooms Ferris walks through nightly (acceptable).
- Small: `d_hatch` "bits of old nest" (nets?); `cm_cottage_wait` "fetch the harbour office here"; jacket versus coat
  across nodes. Recurring numbers are otherwise consistent (43 nights, six winters, 412 crates, 91 steps, the 19th
  step).

## Child-safety flags (for the approver; not defects)

- `tn_gate_wait` and `tn_gate_open`: walking a tide-washed ledge "as if it were a pavement" makes a dangerous act look
  easy.
- `tn_cut_moor` and `cm_cottage`: a child follows a stranger's lantern across a moor alone for an hour and knocks on an
  unknown man's door (it is Ferris, but she does not know it).
- `e_win_promise`: an ongoing arrangement with a man she met once.
- `tn_store`, `tn_store_crate`, `cm_smug` (the radio voice) and the watcher in `e_set_gate` are the most frightening
  content; `e_set_cellar` is moderate.
- Physical peril in `e_set_b_rail`, `e_set_c_tide`, `e_set_c_stuck`, `e_set_fog` and `e_set_gate` is punished, so
  acceptable.

## Why these are useful as known answers

B1 to B3 and S1 are all facts or possessions asserted in a shared node that only some inbound routes or states
establish. That is the defect class a per-book fact ledger with per-node `requires` and `establishes` makes an exact
check (ADR-033), and none of the existing gate, moderation or prose-craft instruments reported any of them.
