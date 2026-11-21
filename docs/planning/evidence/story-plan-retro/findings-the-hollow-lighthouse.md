# WP-0.4 findings: The Hollow Lighthouse

Second-reader continuity pass on `out/the-hollow-lighthouse.filled.json` (pre-fix book: commit `aa5fd8c`, unchanged
since `15b14a1`, sha256 `82817aa48b088b2d5a154d9d76589410c9af376401bde8449c984f9d06561183`), against its hand-written
plan `out/the-hollow-lighthouse.plan.json`. Reader: a different agent from the plan's author. Date: 2026-11-21.
(Written to the repo by the orchestrator from the reader's report, because the harness refused the reader's own write
of this file.)

## Method

- Every reachable (node, variable state) configuration was enumerated with `StoryEngine`: 1,214 pre-fix (162 of 162
  nodes, no dead ends), 1,220 post-fix (164 of 164, no dead ends). Each node was read against every inbound edge and
  every state that reaches it, and each label against the states in which it is visible.
- A mechanical known-on-entry check over (node, state, known set) (union of `establishes` of visited nodes plus the
  plant of each planting choice) checked every node and choice `requires` and every `contradicts` pair: 299,762
  configurations pre-fix, 298,006 post-fix.
- Witness routes below were found by breadth-first search on the pre-fix book. Two prefixes recur:
  - `P_TUN` = `c_open > c_n_start_1 > c_a_office1_1 > c_a_desk_1 > c_a_desk_log_1 > c_a_corridor_1 > c_a_toward_1 >
    c_n_journal_3 > c_jr_tunnel_1 > c_jr_tun_sketch_1 > c_jr_tun_join_1 > c_n_stairs_1 > c_st_wind_1 > c_st_wind_up_1 >
    c_n_light_1 > c_li_stair_1 > c_li_stair_down_1` (arrives at `n_tunnel` with `knows_tunnel`).
  - `P_CODE` = `c_open > c_n_start_1 > c_a_office1_1 > c_a_desk_1 > c_a_desk_log_1 > c_a_corridor_1 > c_a_toward_1 >
    c_n_journal_1 > c_jr_light_1 > c_jr_light_read_1 > c_jr_light_join_1 > c_n_stairs_1 > c_st_wind_1 >
    c_st_wind_up_1 > c_n_light_1 > c_li_stair_1 > c_li_stair_down_1` (arrives at `n_tunnel` with `knows_code`).

Ids B1 to B3, S1 to S4, M1 to M8 are the leads from
`docs/planning/evidence/structural-verification-2026-11-20/lighthouse-continuity-read.md`, verified here. N-ids are
findings this read added. `known-defects.json` was not edited.

## Blockers

### B1 `e_win_keeper_word`: Ferris greets a girl he never met as one he warned

- Route: `P_CODE > c_n_tunnel_3 > c_tn_gate_1 > c_tn_gate_open_1 > c_n_chamber_1 > c_cm_letter_1 >`
  `c_cm_letter_read_1 > c_cm_letter_map_2`; state `knows_code` (any state reproduces).
- Quote: "\"Minded the bog, I see,\" he said."
- Why: the bog warning is spoken only in `cm_cottage_wait`; on the map route Mira never meets Ferris and never walks
  the moor. Reproduced. Also on the `tn_cut_moor > cm_cottage_wait` route she says "the shepherd's cottage", a name
  only the map gives.
- Fix: his line is now "So you are the one who followed my light, ... and then had the sense to fetch help, which is
  more than most of us manage." (true on both inbound routes); "shepherd's cottage" became "the cottage past the second
  gate", and `tn_cut_moor` now passes two gates and a bog. Plan: `ferris_warned_bog` dropped from the ending's
  requires; `tn_cut_moor` establishes `ferris_lives_on_moor`.

### B2 `cm_light_relight` / `e_set_gears`: a key-holder is told she has no key

- Route: `c_open > c_n_start_2 > c_b_lamp1_1 > c_b_lens_2 > c_b_lens_reflect_1 > c_b_down_1 > c_b_down_spiral_1 >
  c_n_journal_3 > c_jr_tunnel_1 > c_jr_tun_sketch_1 > c_jr_tun_join_1 > c_n_stairs_1 > c_st_wind_1 > c_st_wind_up_1 >
  c_n_light_1 > c_li_stair_1 > c_li_stair_down_1 > c_n_tunnel_4 > c_tn_cut_2 > c_n_chamber_3 > c_cm_light_1 >
  c_cm_light_relight_2`; state `has_key, knows_tunnel`.
- Quotes: "\"Where is your key, then?\" Mira asked the lamp." (`cm_light_relight`); "It had wanted a key with a square
  end, and somewhere in this lighthouse there was one." (`e_set_gears`).
- Why: `c_cm_light_relight_2` had no condition, so the reader holding the square-ended key could force the gear and be
  told to go and find one. Reproduced.
- Fix: `c_cm_light_relight_2` is now gated `has_key == false` (a key-holder sees one button, "Wind the clockwork with
  the brass key."); the body line became "\"Square,\" Mira said to the lamp, and looked at the socket for a long
  moment." (true in both states); `e_set_gears` now says "somewhere on this headland" (the keys lie in the cottage,
  caves and boathouse too). `cm_light_back`'s "a key with a tower on it" (a stamp a no-key reader never saw) became "a
  key that fitted this socket". Plan: `mira_lacks_lamp_key` moved from `cm_light_relight` to `cm_light_back`; key thread
  gains the gated payoff.

### B3 `e_win_harbor`: the unknown name and the unseen grey boat

- Routes: name half `c_open > c_n_start_2 > c_b_lamp1_1 > c_b_lens_1 > c_b_lens_crack_1 > c_b_down_2 >
  c_b_down_hatch_1 > c_n_journal_2 > c_jr_smug_2 > c_jr_smug_names_1 > c_jr_smug_join_1 > c_n_stairs_1 > c_st_wind_1 >
  c_st_wind_up_1 > c_n_light_1 > c_li_stair_1 > c_li_stair_down_1 > c_n_tunnel_4 > c_tn_cut_2 > c_n_chamber_2 >
  c_cm_smug_1 > c_cm_smug_photo_2` (state `knows_tunnel, knows_ledger`); boat half `P_TUN > c_n_tunnel_4 > c_tn_cut_2
  > c_n_chamber_2 > c_cm_smug_1 > c_cm_smug_photo_2` (state `knows_tunnel`).
- Quote: "Mira did not know the name. \"He has a grey boat,\" she said,"
- Why: `jr_smug_names` taught the name Varley; on the second route no boat has been seen or mentioned. Reproduced.
- Fix: "Mira told him about the soft voice on the radio that said it could wait. \"He is out there now,\" she said,
  \"in the fog, waiting for the light to change.\"" The radio voice is in `cm_smug`, on every route. Plan: requires
  `radio_voice`; fact `mira_does_not_know_name` deleted.

## Should-fix

### B3-follow `cm_smug_follow`, B3-honest `e_neutral_honest`: the grey boat in narration

- Routes: `P_TUN > c_n_tunnel_4 > c_tn_cut_2 > c_n_chamber_2 > c_cm_smug_2` and the same `> c_cm_smug_follow_2 >
  c_cm_smug_token_2`; state `knows_tunnel`.
- Quotes: "The man with the grey boat had been skimming his own shipments"; "\"Oh, you sneak,\" she said to the man
  with the grey boat."
- Fix: "The man on the radio had been skimming ..."; "... she said to the man on the radio, wherever he was." Plan:
  both require `radio_voice` instead of `grey_boat`.

### S1 `e_win_promise`: where Ferris lives; the journal's place

- Route: `P_TUN > c_n_tunnel_4 > c_tn_cut_2 > c_n_chamber_1 > c_cm_letter_1 > c_cm_letter_read_3 >
  c_cm_letter_plea_1`; state `knows_tunnel`.
- Quotes: "She told the harbour master in the morning, and he fetched the old man down from the moor by noon."; "Then
  she went down to the journal on its stool".
- Why: partly reproduced, as the answer key says. Mira never unfolded the map, so nothing she says tells the harbour
  master where Ferris is. The journal half does not contradict any route, but its location is never fixed after
  `n_journal`, so the line was made location-neutral.
- Fix: "In the morning she gave the harbour master the letter, map and all, and he fetched the old man down from the
  moor by noon."; "under the last line in the keeper's journal, she wrote one of her own". See also child-safety C3.
  Plan: requires `letter_moor_map`, `truth_ferris_sets_blink`.

### S2 `jr_light_read`, `jr_tun_stone`: the code delivered as a first discovery to a reader who already has it

- Routes: `c_open > c_n_start_1 > c_a_office1_2 > c_a_shelf_2 > c_a_shelf_books_1 > c_a_corridor_1 > c_a_toward_1 >
  c_n_journal_1 > c_jr_light_1` (state `knows_code`); `c_open > c_n_start_2 > c_b_lamp1_3 > c_b_clock_2 >
  c_b_clock_chain_1 > c_b_down_1 > c_b_down_spiral_1 > c_n_journal_3 > c_jr_tunnel_2` (state `knows_code`).
- Quotes: "\"It is blinking,\" she said, \"so somebody is being told to keep off, right now.\""; "She read it three
  times, until it stuck."
- Why: confirmed with the answer key's correction (at most two reveal nodes share a path); the second one is the only
  one that can repeat, and these two are the only second-position reveal nodes.
- Fix: "Here it was in the keeper's own hand, and it meant what it had meant all night: somebody out there was being
  told to keep off."; "She read it through twice, slowly, under her breath." Both read true for a first or a second
  meeting.

### S3 `n_chamber`: a store behind her and two lamps she may never have seen

- Route: `P_TUN > c_n_tunnel_4 > c_tn_cut_2`; state `knows_tunnel` (also via `c_tn_gate_open_1`,
  `c_tn_gate_wait_1`, the keeper's-door routes).
- Quote: "there was a store that smelled of tar behind her, two lamps over her head"
- Why: only the `tn_store*` routes came through the store. Also the labels `c_n_chamber_2` "Go back to the store that
  smells of tar." and `c_n_chamber_3` "Climb back up to the two lamps." (the plan already recorded both presuppositions
  as choice requires `store_seen` and `saw_great_lamp`).
- Fix: "Somewhere back along the tunnel was a room that smelled of tar, and over her head were two lamps, one small and
  busy and one great and dark." (`n_tunnel` shows the tar room on every route; the great lamp has stood dark since
  Ferris vanished); labels "Find the store that smells of tar." and "Climb back up toward the lamps." Plan: new fact
  `tar_room_in_tunnel` established by `n_tunnel`; requires updated.

### S4 `e_set_a_drawer`: forks from a kitchen never visited

- Route: `c_open > c_n_start_1 > c_a_office1_1 > c_a_desk_2 > c_a_desk_drawer_2`; all false.
- Quote: "then two forks from the kitchen."
- Fix: "then a hairgrip from her own pocket." Plan: `cottage_kitchen` dropped from requires.

## Minor

- **M1** `c_arch_gap > c_c_arch_gap_1` (route `c_open > c_n_start_3 > c_c_cave1_3 > c_c_arch_2 > c_c_arch_gap_1`, all
  false): "Back out and try the other opening." landed on `c_gather`, which never shows her backing out. Fix: new
  single-choice arrival node `c_arch_back` (she backs out and takes a dry crawl up), flowing into `c_gather`.
- **M2** `tn_gate_open > c_tn_gate_open_1` (route `P_CODE > c_n_tunnel_3 > c_tn_gate_1 > c_tn_gate_open_1`, state
  `knows_code`): "Go now, between two swells." jumped to "Beyond the door", never crossing the ledge or showing a door.
  Fix: new arrival node `tn_gate_dash` (see C1).
- **M3** `e_set_stair` (route: `P_CODE` as far as `c_n_stairs_1`, then `c_st_wind_2`; state `knows_code`): "the
  eighteenth step"; the hollow step in `st_wind` is the nineteenth. Fix: "nineteenth". Plan: fact `hollow_step_18`
  deleted.
- **M4** `cm_light_true` (route `c_open > c_n_start_3 > c_c_cave1_2 > c_c_pool_2 > c_c_pool_metal_1 > c_c_gather_1 >
  c_c_steps_1 > c_n_journal_3 > c_jr_tunnel_1 > c_jr_tun_sketch_1 > c_jr_tun_join_1 > c_n_stairs_1 > c_st_wind_1 >
  c_st_wind_up_1 > c_n_light_1 > c_li_stair_1 > c_li_stair_down_1 > c_n_tunnel_4 > c_tn_cut_2 > c_n_chamber_3 >
  c_cm_light_1 > c_cm_light_relight_1`, state `has_key, knows_tunnel`; also the `d_dinghy_tin` key, which has a note,
  not a tag): "as the tag said, and counted forty turns". The pool key has no tag; forty turns is the little lamp's
  clockwork in `cm_letter_plea`. This is also the plan writer's lead. Fix: "The brass key slid into the square socket
  ... Mira wound the clockwork slowly, the way a stiff old thing likes to be wound, until the key would turn no more."
  Plan: `key_tag` dropped from requires.
- **M5** `tn_store_box > c_tn_store_box_1` (route `P_CODE > c_n_tunnel_2 > c_tn_store_2 > c_tn_store_box_1`): "Take
  the ledger through the low doorway." The ledger is never mentioned again. Fix: label "Leave the ledger in its box and
  duck through the low doorway."
- **M6** `tn_gate`: two consecutive sentences open "Mira". Fix: the second opens "She"; the buoy sentence was
  lengthened to keep the node inside the reading band.
- **M7** `e_win_signal`: titled "The Signal Solved" while it closes on who wound the clockwork. Fix: ending title "The
  Ghost on Paper" (the ending solves the machine, not the keeper); id, kind and valence unchanged.
- **M8** dust in rooms Ferris uses: checked, not a defect. Ferris passes the keeper's room by its side door
  (`tn_keep_side`: bootprints pass the door) and has never entered the store (`jr_smug_torn`); the keeper's room and
  store are the only dusty rooms.
- **Small** `d_hatch` (route `c_open > c_n_start_4 > c_d_boat1_1 > c_d_dinghy_1 > c_d_dinghy_tarp_1`): "bits of old
  nest" read as a typo. Fix: "bits of old birds' nest". `cm_cottage_wait`: "fetch the harbour office here". Fix: "fetch
  the harbour master up here". `cm_letter`, `c_cm_letter_2`, `cm_letter_keep` call Mira's jacket (as named in
  `b_gallery`, `li_ladder`, `e_set_c_stuck`, `e_set_beam`, `e_neutral_museum`) a coat. Fix: "jacket".

## Findings this read added

- **N1** `cm_light_study` (route `P_TUN > c_n_tunnel_4 > c_tn_cut_2 > c_n_chamber_3 > c_cm_light_2`, state
  `knows_tunnel`): "It reached the harbour, and it reached the boat." No boat has been seen or mentioned on this route.
  Fix: "and it reached anyone out on the water."
- **N2** `cm_smug_photo` (route `P_TUN > c_n_tunnel_4 > c_tn_cut_2 > c_n_chamber_2 > c_cm_smug_1`, state
  `knows_code` false): "the lamp ... went on saying the same two words." Mira cannot know the blink says "keep off"
  without the code. Fix: "went on saying the same thing, over and over." (split into two sentences for reading level).
- **N3** `b_gallery_fog` (route `c_open > c_n_start_2 > c_b_lamp1_2 > c_b_gallery_2 > c_b_gallery_fog_1 > c_b_down_1 >
  c_b_down_spiral_1 > c_n_journal_1 > c_jr_light_1 > c_jr_light_read_1 > c_jr_light_join_1 > c_n_stairs_1 >
  c_st_wind_1 > c_st_wind_up_1`, state `knows_code`): "at the very foot of the tower, a thin green glow leaked out of an
  iron grille ... It began somewhere in the foundations". The same route then climbs a stair from the landing at the
  tower's foot to the rig in `n_light`, which sits fifty rungs above the undercroft. Fix: "low on the tower's side, ...
  out of a small window"; "It began somewhere low in the tower". Plan: `light_from_foundations` text updated.
- **N4** `cm_smug`, `cm_smug_hoard`, `e_win_hoard` (route `P_TUN > c_n_tunnel_4 > c_tn_cut_2 > c_n_chamber_2`):
  "something heavy had left drag marks in the dust." Fresh marks through a year of dust contradict the truth that
  nobody has touched the cargo in a year (`e_win_ledger`: "He has not touched any of it in a year"). Fix: the marks are
  old, with dust settled back into them, in all three nodes.
- **N5** `e_set_cellar` (route `c_open > c_n_start_1 > c_a_office1_1 > c_a_desk_1 > c_a_desk_log_1 > c_a_corridor_1 >
  c_a_toward_1 > c_n_journal_2 > c_jr_smug_2 > c_jr_smug_names_1 > c_jr_smug_join_2`, state `knows_ledger`): "Then the
  green flicker on the stair went out". No green flicker was shown on the `jr_smug_join` route. Fix: "Then, up the open
  panel stair, a faint green glow went out".
- **N6** plan writer's lead, `cm_letter_read` reveals "blinking means keep off" without setting `knows_code`: verified,
  not a continuity defect. No passage after `cm_letter_read` says or implies that Mira does not know the meaning, and the
  hidden choice "Tell him the light says keep off." also needs "steady, he lands", which the letter does not give. No
  change.

## Child safety (launch-message flags)

- **C1** `tn_gate_open`, `tn_gate_wait` (route `P_CODE > c_n_tunnel_3 > c_tn_gate_1 > c_tn_gate_open_2`, state
  `knows_code, knows_ledger`): "she walked its ten paces as if it were a pavement" made crossing a wave-washed ledge look
  easy, and the dash choice crossed with no cost at all. Fix: the ledge is sloping, slimy and washed over; "the worst ten
  paces Mira had ever looked at"; she goes ring to ring, is soaked to the knees and scrambles up shaking; the dash now
  passes through `tn_gate_dash`, where she slips, is caught to the knees by a swell, clings with her eyes shut and says
  "Never again". Nothing more frightening than `e_set_gate`, which already exists.
- **C2** `tn_cut_moor`, `cm_cottage` (route `P_TUN > c_n_tunnel_4 > c_tn_cut_1 > c_tn_cut_moor_1`, state
  `knows_tunnel`): "Far ahead a small yellow lantern bobbed ... She walked after it for the better part of an hour"
  then "Mira knocked" at an unknown man's door. It read as a child following a stranger's light. Fix: she follows the
  keeper's prints in the grey of morning, knowing whose way it is, "did not try to catch him up", means "only ... to see
  where he went, so that she could tell the harbour office exactly where to look", and keeps "well back on the open
  track". At the cottage she knocks "and then stepped back down the path to the gate, with the whole open hillside behind
  her" (label "Knock, then step back to the gate."); the door stays bolted, and `cm_cottage_light` now says she is at the
  gate, not on the step. The existing choice to tell him to stay bolted in while she fetches help is unchanged.
- **C3** `e_win_promise` (listed for the approver in the continuity read): "this time there were two sets of bootprints
  on the stair" implied a continuing night-time arrangement between a child and a man. Fix: "word came up from the
  harbour that the pale light had blinked all night over the sea, right on time. The old keeper was well, and the promise
  could wait."

## Post-fix re-read

Every changed and added node was re-read against every inbound edge and state, and the full configuration walk and
known-on-entry check were re-run on the fixed book: 1,220 configurations, no dead ends, no unmet node or choice requires,
no contradicting facts on any route. Two seams the reader's own edits introduced were found and fixed before closing
("standing on my step" after she had stepped back to the gate; "furred with dust" twice in `cm_smug`). Open findings:
zero. `scripts/check_story_plan.py` reports zero errors and zero warnings on the fixed book and plan.
