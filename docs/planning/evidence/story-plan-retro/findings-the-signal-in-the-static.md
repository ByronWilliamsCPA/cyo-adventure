# WP-0.4 continuity read: The Signal in the Static (revised edition)

Second-reader continuity pass over `out/the-signal-in-the-static.filled.json` against its hand-written plan
`out/the-signal-in-the-static.plan.json`, 2026-11-21, WP-0.4 of `docs/planning/story-plan-implementation-plan.md`.
The reader did not write the plan or the revision. (Written to the repo by the orchestrator from the reader's report,
because the harness refused the reader's own write of this file.)

**Pre-fix book.** Blob at commit `aa5fd8c` (unchanged since `5eae618`), SHA-256
`f0c851f90618cb43b7a7891e3e13cd6e8c3c9ac5c59ff337f6643be7cb1da5db`, 139 nodes, 35 endings, four booleans
(`has_battery` and `has_headset` mutually exclusive, `left_note`, `okafor_trust`).

**Method.** `StoryEngine` walked every route from `n_open`: 56,834 routes, 662 reachable (node, state) configurations,
139/139 nodes, 35/35 endings, no dead ends. Per configuration, the plan's known-on-entry set (route `establishes` plus
the plant facts of planting choices taken) was intersected across routes and compared with `requires`: 24 failures,
all on four nodes. Every body and label was then read against its inbound routes and states for untracked facts,
contradictions with `truth` and the editor's world facts, objects or people from nowhere, and timeline slips. Witnesses
are the shortest found by BFS on the pre-fix book.

Route abbreviations:

- `H` = `c_open > c_n_shelf_1 > c_n_shelf_battery_1 > c_n_start_1 > c_r_coord_1_1 > c_r_coord_harbor_1 >
  c_r_coord_harbor_ask_1 > c_r_coord_beat_1 > c_r_coord_close_1`
- `Hh` = `H` with `c_n_shelf_2 > c_n_shelf_headset_1` in place of the battery pair
- `S` = `c_n_b1_2 > c_n_b1_slip_1 > c_n_b1_echo_1 > c_n_b1_choice_1`
- `N` = `c_n_b1_1 > c_n_b1_note_1 > c_n_b1_echo_1`
- `C` = `c_m_numbers_1_1 > c_m_num_cipher_1 > c_m_num_cracked_1`
- `D` = `c_n_b2_1 > c_n_b2_echo_1 > c_n_b2_choice_1 > c_mm_listener_1_1 > c_mm_list_family_1 > c_mm_list_daughter_1 >
  c_n_b3_1 > c_n_b3_echo_1`

## Blockers

| Id | Node | Sentence (pre-fix) | Route and state | Why it is wrong | Fix applied |
| --- | --- | --- | --- | --- | --- |
| B1 | `f_he_act` | "Occupied building, headland, spring tide plus gale, stand by." | `H > S > C > D > c_n_b3_choice_3 > c_f_help_1_1 > c_f_he_cg_1`; `has_battery` (every `has_headset` state too) | `requires: spring_tide_tonight`, established only at `mm_count_tide`; Wren is said to give a hazard only the tide-table reader knows. | Wren gives the relay, an old man alone, a gale coming, twenty to midnight; the officer works out the spring tide from the hour. Node now establishes `spring_tide_tonight`, requires `gale_tonight`. |
| B2 | `e_he_safe` | "to ask how a schoolgirl knew to start with the tide." | B1 route `> c_f_he_act_2`; any state | Same unearned fact; after B1 the officer raised the tide. | "to ask how a schoolgirl knew to give him the place, the danger and the hour before anything else." |
| B3 | `e_re_photo` | "It stops two nights later, in the middle of a number," | `c_open > c_n_shelf_1 > c_n_shelf_battery_1 > c_n_start_2 > c_r_relay_1_1 > c_r_re_path_2`; any state | Zero is tonight on every path: photo on night one, zero at 23:40 the next night. | "It stops the very next night, in the middle of a number," |
| B4 | `m_numbers_1` (+ `m_num_cipher`, `m_num_cracked`, `c_m_numbers_1_1`, `c_m_num_cipher_1`) | "Old operators loved a book cipher, in which every group points to a page and a line in some book that both ends own, and her grandfather's logbook lies by her elbow, crammed with his cramped handwriting." | `H > N > c_n_b1_choice_1`; any state (every route skipping `r_no_trunk`) | Logbook in hand on routes that never found it; and a cipher defined as keyed to a shared book then decodes against Grandpa's private logbook. | Logbook "fetched down from the cedar trunk in the attic", with "the club's printed station register" tucked in its back cover; cipher, labels and `m_num_cracked` key to the register. New plan fact `station_register`. |
| B5 | `n_b2_under` | "Wren sits very still, because the woman reading the numbers was a girl once, and she called the man at that station Dad." | `Hh > N > c_n_b1_choice_1 > C > c_n_b2_2`; `has_headset` | The numbers voice is Marin at seventeen (`e_re_found`); the sentence makes the reader a grown woman. | "because the voice reading the numbers belongs to a girl not much older than she is, and that girl called the man at that station Dad." |

## Should-fix

| Id | Node | Sentence (pre-fix) | Route and state | Why it is wrong | Fix applied |
| --- | --- | --- | --- | --- | --- |
| S1 | `e_re_answer` | "older than the one that reads the numbers but with the very same careful vowels." ... "a father who has kept her voice on a loop for thirty years." | `H > S > C > c_n_b2_1 > c_n_b2_echo_1 > c_n_b2_choice_1 > c_mm_listener_1_1 > c_mm_list_family_2 > c_mm_list_sister_1 > c_n_b3_1 > c_n_b3_echo_1 > c_n_b3_choice_2 > c_f_relay_1_1 > c_f_re_rig_1 > c_f_re_boost_1`; `has_battery` | `requires: voice_is_daughter`, unearned on battery routes skipping `mm_list_daughter`. | Recognition happens in scene: "so that there is no mistaking whose voice the loop has been keeping." Node now establishes `voice_is_daughter`, requires only `m_is_marin`. |
| S2 | `f_he_cg` | "all she can hear is a girl's voice counting," | same prefix `... > c_n_b3_choice_3 > c_f_help_1_1`; `has_battery` | Soft: leans on the speaker's identity; every route has heard "a woman's careful voice". | "that careful voice counting"; `requires` dropped. |
| S3 | `mm_listener_1` | "all Wren has to start from is a single letter." | `H > N > c_n_b1_choice_2 > c_m_who_1_2 > c_m_who_okafor_1 > c_m_who_story_1 > c_n_b2_1 > c_n_b2_echo_1 > c_n_b2_choice_1`; `okafor_trust` (also the headset route through `c_n_b2_2 > c_n_b2_under_1`) | She knows of the daughter, or heard a girl call him Dad. | "the loop itself gives her only a single letter." |
| S4 | `mm_count_1` | "Her grandfather's tide table hangs on its nail by the window," | `H > N > c_n_b1_choice_1 > c_m_numbers_1_1 > c_m_num_cipher_2 > c_m_num_book2_1 > c_m_num_cracked2_1 > c_n_b2_1 > c_n_b2_echo_1 > c_n_b2_choice_2`; any state | His tide table was the battered book from the shelf; a second one appears. | "This year's tide table hangs on its nail by the window," |
| S5 | `mm_count_tide` | "the low end of that service lane on a calm day," | `H > N > c_n_b1_choice_1 > C > c_n_b2_1 > c_n_b2_echo_1 > c_n_b2_choice_2 > c_mm_count_1_2`; any state | Only `r_re_lane` readers know a service lane. | "the low road under the headland" |
| S6 | `e_st_wait` | "a voice she knows from one recorded sentence" | `H > S > C > D > c_n_b3_choice_1 > c_f_station_1_2 > c_f_st_road_2`; any state | The `n_b3` tape is several sentences. | "a voice she knows from the tape an hour ago" |
| S7 | `e_st_record` | "Her phone is still recording in her jacket pocket," | `Hh > S > C > c_n_b2_2 > c_n_b2_under_1 > c_n_b2_echo_1 > c_n_b2_choice_1 > c_mm_listener_1_1 > c_mm_list_family_1 > c_mm_list_daughter_1 > c_n_b3_1 > c_n_b3_echo_1 > c_n_b3_choice_1 > c_f_station_1_1 > c_f_st_fence_1 > c_f_st_control_2 > c_f_st_power_2`; `has_headset` | She never started a recording on any route. | "She thumbed her phone to record as she ran in from the yard, so that single word, at least, has been saved in her jacket pocket." |
| S8 | `n_b3_choice` | "and a daughter who is not listening." | `H > S > C > D`; any state | Narration asserts Kell's belief; endings show Marin listening (`e_re_found`, `e_st_alder_send`, `e_st_note`, `e_no_cards_end`, `e_re_message`). | "a daughter who may not be listening."; plan `pitch.stake` updated. |
| S9 | `mm_list_daughter` | "the person it is meant for has spent thirty years somewhere it cannot reach her." | `H > N > c_n_b1_choice_1 > C > c_n_b2_1 > c_n_b2_echo_1 > c_n_b2_choice_1 > c_mm_listener_1_1 > c_mm_list_family_1`; any state | Same contradiction as S8, on a single path with `e_re_found`. Found on second read. | "and nobody knows whether, in thirty years, it has ever once reached her." |

## Minor

| Id | Node | Finding | Fix applied |
| --- | --- | --- | --- |
| M1 | `n_open` | "a woman's flat, careful voice" vs Marin at seventeen. | "a young woman's"; plan facts `loop_nightly`, `voice_is_daughter` ("recorded at seventeen"). |
| M2 | `r_coord_base_out` into `r_coord_beat` | Route `c_open > c_n_shelf_1 > c_n_shelf_battery_1 > c_n_start_1 > c_r_coord_1_2 > c_r_coord_tower_2 > c_r_coord_base_2 > c_r_coord_base_out_1`: flowed nodes both say "With every hundred yards the loop ...". | "As she walks, the loop steadies in her earbuds." |
| M3 | `e_who_warn` title | "Sent Home to Bed" in a five o'clock scene. | "Not for a School Project". |
| M4 | `e_he_complete` title | "Two People There" vs "It takes all three of them." | "It Takes All Three". |
| M5 | `m_numbers_1`, `f_he_act` | Second read: "the logbook is under her hand" after the key moved; "old relay ... old man". | "the register is under her hand"; "the relay station on the headland". |

## Leads verified

- Spring tide (`f_he_act`, `e_he_safe`): confirmed, B1 and B2. Marin's voice (`e_re_answer`): confirmed, S1;
  `f_he_cg` soft, S2.
- Editor world facts all hold on every path that mentions them:
  - Marin at seventeen (after B5 and M1).
  - Two dots at midnight (`e_no_locked`, `e_st_note`; `r_no_tuning` and `r_no_freq` do not contradict it).
  - Card signed M (`e_no_cards_end`; Okafor's "never wrote" refers to her father).
  - Okafor pins the card monthly (`m_who_story`; `r_coord_notice2` and `e_coord_notice` fit).
  - Fence route: Alder at the mast (`f_st_control`, `e_st_hesitate`, `e_st_stabilize`). Road route: at the console
    (`f_st_road`, `e_st_wait`). Phone and Okafor routes: at the console.
  - Zero is tonight (after B3).
- Hub summaries: `r_coord_beat`, `r_relay_beat`, `r_notes_beat`, `n_b1`, `n_b1_choice`, `n_b2`, `n_b2_choice`, `n_b3`
  and `n_b3_choice` assert only what every inbound route earned. "Thirty years" is earned at `n_b1`, "M" at `n_b2`
  (the Morse chart), "Marin" at `n_b3` (the tape).

## After the fix

Every `requires` holds on entry in all 662 configurations (24 failures before, 0 after). The second full read found
only S9 and M5, which were fixed in the same pass. Open findings: 0. `scripts/check_story_plan.py` reports zero errors
on the fixed book and plan.
